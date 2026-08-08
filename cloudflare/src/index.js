/**
 * API del tablero CREAN sobre Cloudflare D1.
 *
 * Dos reglas gobiernan todo este archivo:
 *
 * 1. TODA consulta lleva indice y LIMIT. D1 factura por filas leidas
 *    (5 millones/dia en el plan gratuito) y la tabla `cliente` tiene 860.223
 *    filas: un solo SELECT sin filtro consumiria el 17% del presupuesto diario.
 *
 * 2. `numero_id` NUNCA se convierte a numero. Llega a +-9,2e18 y el entero
 *    exacto maximo de JavaScript es 9,007e15. Convertirlo le cambiaria los
 *    ultimos digitos en silencio y devolveriamos identificadores inexistentes.
 *    Se guarda como TEXT en D1 y se maneja como string de punta a punta.
 */

const TOPE_LISTA = 500; // filas maximas por peticion de lista

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "public, max-age=300",
};

function json(datos, status = 200) {
  return new Response(JSON.stringify(datos), { status, headers: JSON_HEADERS });
}

function error(mensaje, status = 400) {
  return json({ error: mensaje }, status);
}

/** Lista de valores desde un parametro repetible o separado por comas. */
function multiple(url, nombre) {
  const crudo = url.searchParams.getAll(nombre);
  const partes = crudo.flatMap((v) => v.split(",")).map((v) => v.trim());
  return partes.filter(Boolean);
}

/** Marcadores `?,?,?` para un IN, con sus valores. Nunca se interpola texto. */
function clausulaIn(columna, valores) {
  const marcadores = valores.map(() => "?").join(", ");
  return { sql: `${columna} IN (${marcadores})`, valores };
}

// ---------------------------------------------------------------- endpoints

async function resumen(env) {
  const [claves, tasas, curva] = await env.DB.batch([
    env.DB.prepare("SELECT clave, valor FROM resumen"),
    env.DB.prepare(
      "SELECT variable, categoria, tasa_adopcion, n_clientes FROM tasa_segmento"
    ),
    env.DB.prepare(
      "SELECT top_pct, n_contactados, precision_, recall_ FROM curva_esfuerzo ORDER BY top_pct"
    ),
  ]);

  const cifras = {};
  for (const fila of claves.results) cifras[fila.clave] = fila.valor;

  const poblaciones = await env.DB.prepare(
    `SELECT poblacion,
            COUNT(*) AS n,
            SUM(con_inversion) AS con_inversion
     FROM cliente GROUP BY poblacion`
  ).all();

  return json({
    cifras,
    tasas: tasas.results,
    curva: curva.results,
    poblaciones: poblaciones.results,
  });
}

async function dimensionamiento(env) {
  const r = await env.DB.prepare(
    "SELECT * FROM dimensionamiento ORDER BY nivel, poblacion, desc_segmento"
  ).all();
  return json(r.results);
}

async function validacion(env) {
  const r = await env.DB.prepare(
    "SELECT * FROM validacion ORDER BY iv DESC"
  ).all();
  return json(r.results);
}

async function importancia(env, url) {
  const modelo = url.searchParams.get("modelo") || "A";
  const r = await env.DB.prepare(
    `SELECT variable, importancia, iv, decision_inclusion
     FROM importancia WHERE modelo = ?
     ORDER BY importancia DESC LIMIT 15`
  )
    .bind(modelo)
    .all();
  return json(r.results);
}

async function sesgo(env) {
  const r = await env.DB.prepare("SELECT * FROM sesgo").all();
  return json(r.results);
}

/** Opciones de los filtros. Se leen de indices, no de la tabla completa. */
async function facetas(env) {
  const [pobl, niv, seg] = await env.DB.batch([
    env.DB.prepare("SELECT DISTINCT poblacion FROM cliente ORDER BY poblacion"),
    env.DB.prepare("SELECT DISTINCT nivel FROM cliente ORDER BY nivel"),
    env.DB.prepare(
      "SELECT DISTINCT desc_segmento FROM cliente WHERE desc_segmento IS NOT NULL ORDER BY desc_segmento"
    ),
  ]);
  return json({
    poblaciones: pobl.results.map((r) => r.poblacion),
    niveles: niv.results.map((r) => r.nivel),
    segmentos: seg.results.map((r) => r.desc_segmento),
  });
}

const TOTAL_CLIENTES = 860223;

async function clientes(env, url) {
  const condiciones = [];
  const valores = [];

  for (const [param, columna] of [
    ["poblacion", "poblacion"],
    ["nivel", "nivel"],
    ["segmento", "desc_segmento"],
  ]) {
    const elegidos = multiple(url, param);
    if (elegidos.length) {
      const c = clausulaIn(columna, elegidos);
      condiciones.push(c.sql);
      valores.push(...c.valores);
    }
  }
  const soloConMonto = url.searchParams.get("con_monto") === "1";
  if (soloConMonto) condiciones.push("con_inversion = 1");

  const limite = Math.min(
    parseInt(url.searchParams.get("limit") || "100", 10) || 100,
    TOPE_LISTA
  );
  const donde = condiciones.length ? `WHERE ${condiciones.join(" AND ")}` : "";

  // El total sale de `conteo`, que tiene 24 filas. Contarlo sobre `cliente`
  // costaria leer una entrada de indice por cada coincidencia: 215.057 en el
  // filtro por defecto, en cada carga de pagina.
  const agregado = await env.DB.prepare(
    `SELECT COALESCE(SUM(${soloConMonto ? "n_con_inversion" : "n"}), 0) AS n,
            COALESCE(SUM(entrada_bruta), 0) AS entrada
     FROM conteo ${donde}`
  )
    .bind(...valores)
    .first();
  const total = agregado?.n ?? 0;

  // Dos caminos posibles y se elige el barato:
  //
  //  · recorrer el indice de percentil en orden y descartar lo que no cumple
  //    cuesta aproximadamente  N x limite / total  filas
  //  · filtrar por el indice compuesto y ordenar en memoria cuesta  total
  //
  // El cruce esta en  total > sqrt(N x limite). Medido sobre los datos
  // reales: con "nivel A" recorrer lee 100 filas contra 215.057 de la otra
  // via; con un filtro que devuelve 47 clientes, recorrer leeria la tabla
  // entera y filtrar lee 47. La regla acierta en ambos extremos.
  const recorrerIndice = total > Math.sqrt(TOTAL_CLIENTES * limite);
  const indice = recorrerIndice ? "idx_cliente_percentil" : "idx_cliente_filtro";

  const filas = await env.DB.prepare(
    `SELECT numero_id, poblacion, nivel, desc_segmento, grupo_edad, score,
            modelo_usado, monto_base_12m, valor_esperado_12m, percentil_en_grupo
     FROM cliente INDEXED BY ${indice} ${donde}
     ORDER BY percentil_en_grupo DESC
     LIMIT ?`
  )
    .bind(...valores, limite)
    .all();

  return json({
    filas: filas.results,
    total,
    entrada_bruta: agregado?.entrada ?? 0,
    limite,
    estrategia: recorrerIndice ? "recorrido_ordenado" : "filtro_y_orden",
  });
}

async function cliente(env, url) {
  const id = (url.searchParams.get("id") || "").trim();
  // Se valida como cadena de digitos: nunca se convierte a Number.
  if (!/^-?\d{1,20}$/.test(id)) return error("identificador invalido", 422);

  const fila = await env.DB.prepare(
    `SELECT numero_id, poblacion, nivel, desc_segmento, grupo_edad, score,
            modelo_usado, monto_base_12m, valor_esperado_12m, percentil_en_grupo
     FROM cliente WHERE numero_id = ?`
  )
    .bind(id)
    .first();

  if (!fila) return error("cliente no encontrado", 404);
  return json(fila);
}

// ------------------------------------------------------------------ router

const RUTAS = {
  "/api/resumen": (env) => resumen(env),
  "/api/dimensionamiento": (env) => dimensionamiento(env),
  "/api/validacion": (env) => validacion(env),
  "/api/sesgo": (env) => sesgo(env),
  "/api/facetas": (env) => facetas(env),
  "/api/importancia": (env, url) => importancia(env, url),
  "/api/clientes": (env, url) => clientes(env, url),
  "/api/cliente": (env, url) => cliente(env, url),
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!url.pathname.startsWith("/api/")) {
      return env.ASSETS.fetch(request);
    }
    if (request.method !== "GET") {
      return error("solo se admite GET", 405);
    }

    const manejador = RUTAS[url.pathname];
    if (!manejador) return error("ruta no encontrada", 404);

    try {
      return await manejador(env, url);
    } catch (e) {
      // El detalle va a los logs (observability), no a la respuesta.
      console.error(url.pathname, e);
      return error("error consultando la base de datos", 500);
    }
  },
};
