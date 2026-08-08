/**
 * Tablero CREAN — capa de presentación.
 *
 * Sin framework y sin paso de compilación a propósito: el contenido es
 * mayormente estático y las partes dinámicas son media docena de consultas.
 *
 * REGLA QUE NO SE PUEDE ROMPER: `numero_id` se trata SIEMPRE como texto.
 * Llega a ±9,2e18 y el entero exacto máximo de JavaScript es 9,007e15, así que
 * cualquier `Number(id)` le cambiaría los últimos dígitos en silencio.
 */

// --------------------------------------------------------------- utilidades
const $ = (sel) => document.querySelector(sel);

const FMT = new Intl.NumberFormat("es-CO");

function miles(n) {
  return n === null || n === undefined ? "—" : FMT.format(Math.round(n));
}

/** Pesos en la escala que se lee sin contar ceros (convención colombiana). */
function cop(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const signo = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1e12) return `${signo}$${(a / 1e12).toFixed(2)} billones`;
  if (a >= 1e9) return `${signo}$${(a / 1e9).toFixed(1)} mil M`;
  if (a >= 1e6) return `${signo}$${(a / 1e6).toFixed(1)} M`;
  return `${signo}$${FMT.format(Math.round(a))}`;
}

const pct = (v, d = 1) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);

function progresoPct(v) {
  const n = Math.max(0, Math.min(1, Number(v) || 0));
  return `<span class="mini-progreso"><span style="width:${(n * 100).toFixed(2)}%"></span></span>
    <span class="mini-progreso-texto">${pct(n, 2)}</span>`;
}

/** Escapa texto antes de insertarlo como HTML. */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(ruta) {
  const r = await fetch(ruta);
  if (!r.ok) throw new Error(`${ruta} respondió ${r.status}`);
  return r.json();
}

function kpi(rotulo, valor, detalle = "") {
  return `<div class="kpi"><div class="r">${esc(rotulo)}</div>
    <div class="v">${esc(valor)}</div>
    ${detalle ? `<div class="d">${esc(detalle)}</div>` : ""}</div>`;
}

function panelModelo(rotulo, auc, detalle, nota) {
  return `<div class="panel-modelo"><strong>${esc(rotulo)}</strong>
    <div class="auc">${esc(auc)}</div>
    <p>${esc(detalle)}</p>
    <p>${esc(nota)}</p></div>`;
}

/**
 * Pinta una tabla. `formato` puede dar una función por columna; lo que esa
 * función devuelve se inserta como HTML, así que debe escapar lo que venga de
 * la base de datos. Sin función, el valor se escapa aquí.
 */
function tabla(destino, columnas, filas, formato = {}) {
  const th = columnas.map((c) => `<th>${esc(c.titulo)}</th>`).join("");
  const cuerpo = filas
    .map((f) => {
      const tds = columnas
        .map((c) => {
          const bruto = f[c.campo];
          const v = formato[c.campo]
            ? formato[c.campo](bruto, f)
            : esc(bruto ?? "—");
          return `<td class="${c.clase || ""}">${v}</td>`;
        })
        .join("");
      return `<tr>${tds}</tr>`;
    })
    .join("");
  destino.innerHTML = `<thead><tr>${th}</tr></thead><tbody>${cuerpo}</tbody>`;
}

/** Barras horizontales con línea de referencia opcional. */
function barras(destino, filas, { etiqueta, valor, maximo, referencia, formato }) {
  const tope = maximo ?? Math.max(...filas.map((f) => f[valor])) * 1.05;
  destino.innerHTML = filas
    .map((f) => {
      const ancho = Math.max(0, Math.min(100, (f[valor] / tope) * 100));
      const ref = referencia
        ? `<div class="referencia" style="left:${(referencia / tope) * 100}%"></div>`
        : "";
      return `<div class="barra">
        <span class="etq">${esc(f[etiqueta])}</span>
        <span class="pista"><span class="relleno" style="width:${ancho}%"></span>${ref}</span>
        <span class="val">${formato(f[valor])}</span>
      </div>`;
    })
    .join("");
}

function fallo(destino, e) {
  destino.innerHTML = `<div class="error">No se pudieron cargar los datos.
    ${esc(e.message)}</div>`;
}

// -------------------------------------------------------------- navegación
const cargadas = new Set();

function mostrar(nombre) {
  document.querySelectorAll("main section").forEach((s) => {
    s.hidden = s.id !== nombre;
  });
  document.querySelectorAll("nav button").forEach((b) => {
    b.setAttribute("aria-current", String(b.dataset.vista === nombre));
  });
  if (location.hash !== `#${nombre}`) history.replaceState(null, "", `#${nombre}`);
  if (!cargadas.has(nombre)) {
    cargadas.add(nombre);
    (CARGA[nombre] || (() => {}))();
  }
}

document.querySelectorAll("nav button").forEach((b) => {
  b.addEventListener("click", () => mostrar(b.dataset.vista));
});

// ------------------------------------------------------------------ vistas
let RESUMEN = null;

async function datosResumen() {
  if (!RESUMEN) RESUMEN = await api("/api/resumen");
  return RESUMEN;
}

const CARGA = {
  async resumen() {
    try {
      const d = await datosResumen();
      const c = d.cifras;
      $("#kpis-resumen").innerHTML =
        kpi("Clientes analizados", miles(c.n_clientes_total), "el 100% de la base") +
        kpi("Oportunidad de captación", cop(c.entrada_bruta_12m),
            `${miles(c.n_clientes_entrada)} clientes crecerían`) +
        kpi("Prioridad alta", miles(c.n_nivel_A), "clientes en nivel A") +
        kpi("Aciertos del modelo", c.auc_modelo_a.toFixed(3), "capacidad de discriminación");

      const conInv = d.poblaciones.find((p) => p.poblacion === "con_historial");
      const sinProd = d.poblaciones.find((p) => p.poblacion === "sin_historial");
      const filas = [
        { e: "Adquisición", q: "Sin ningún producto", n: sinProd?.n ?? 0,
          m: "No estimable" },
        { e: "Activación", q: "Clientes sin inversión",
          n: (conInv?.n ?? 0) - (conInv?.con_inversion ?? 0), m: "No estimable" },
        { e: "Crecimiento", q: "Ya invierten", n: conInv?.con_inversion ?? 0,
          m: "Estimado" },
      ];
      tabla($("#tabla-poblaciones"),
        [{ titulo: "Estrategia", campo: "e" }, { titulo: "Quiénes son", campo: "q" },
         { titulo: "Clientes", campo: "n", clase: "num" },
         { titulo: "¿Monto?", campo: "m" }],
        filas, { n: (v) => miles(v) });
    } catch (e) { fallo($("#kpis-resumen"), e); }
  },

  async clientes() {
    try {
      const d = await datosResumen();
      const base = d.cifras.tasa_adopcion;
      $("#nota-tasa-base").innerHTML =
        `En todos los gráficos la <b>línea roja</b> marca el promedio general:
         <b>${pct(base)}</b> de los clientes invierte hoy. Estar por encima
         significa invertir más que el promedio. Sin esa referencia un
         porcentaje suelto no dice nada.`;

      const por = (v) => d.tasas.filter((t) => t.variable === v)
        .sort((a, b) => b.tasa_adopcion - a.tasa_adopcion);
      const opts = { etiqueta: "categoria", valor: "tasa_adopcion",
        referencia: base, formato: (v) => pct(v) };
      barras($("#barras-segmento"), por("desc_segmento"), opts);
      barras($("#barras-edad"), por("grupo_edad"), opts);
      barras($("#barras-genero"), por("desc_genero"), opts);
      barras($("#barras-vivienda"), por("desc_tipo_de_vivienda"), opts);
    } catch (e) { fallo($("#barras-segmento"), e); }
  },

  async solucion() {
    try {
      const d = await datosResumen();
      const c = d.cifras;
      $("#kpis-modelos").innerHTML =
        panelModelo("Modelo A · probabilidad", c.auc_modelo_a.toFixed(3),
            `${c.n_features_a} variables · 529.470 clientes con productos`,
            "Entrega una probabilidad real de adopción.") +
        panelModelo("Modelo B · parecido", c.auc_modelo_b.toFixed(3),
            `${c.n_features_b} variables · 330.753 clientes sin productos`,
            "Ordena adquisición en frío; no promete conversión.");

      const val = await api("/api/validacion");
      tabla($("#tabla-validacion"),
        [{ titulo: "Variable", campo: "variable" },
         { titulo: "IV", campo: "iv", clase: "num" },
         { titulo: "Fuerza", campo: "clase_iv" },
         { titulo: "VIF", campo: "vif", clase: "num" },
         { titulo: "Decisión", campo: "decision_inclusion" }],
        val,
        { iv: (v) => (v ?? 0).toFixed(3),
          vif: (v) => (v === null ? "—" : Number(v).toFixed(1)) });

      const pintarImportancia = async () => {
        const m = $("#sel-modelo").value;
        const imp = await api(`/api/importancia?modelo=${encodeURIComponent(m)}`);
        barras($("#barras-importancia"), imp, {
          etiqueta: "variable", valor: "importancia",
          formato: (v) => v.toFixed(4) });
      };
      $("#sel-modelo").addEventListener("change", pintarImportancia);
      await pintarImportancia();
    } catch (e) { fallo($("#kpis-modelos"), e); }
  },

  async oportunidad() {
    try {
      const d = await datosResumen();
      const c = d.cifras;
      $("#respuesta-oportunidad").innerHTML =
        `<span class="rotulo">En corto</span>
         Los clientes que ya invierten y que el modelo proyecta creciendo
         moverían <b>${cop(c.entrada_bruta_12m)} de pesos</b> en los próximos 12
         meses. Ese es el tamaño de la mesa. Cuánto de eso capta efectivamente
         la App <b>no lo puede decir un modelo de saldos</b>: depende de qué tan
         bien se lance el producto.`;

      $("#kpis-oportunidad").innerHTML =
        kpi("Dinero que podría entrar", cop(c.entrada_bruta_12m),
            `${miles(c.n_clientes_entrada)} clientes crecerían`) +
        kpi("Dinero que podría salir", cop(c.salida_bruta_12m),
            `${miles(c.n_clientes_salida)} clientes retirarían`) +
        kpi("Diferencia neta", cop(c.neto_12m), "entrada menos salida");

      const slider = $("#captura");
      const pintar = () => {
        const t = Number(slider.value) / 100;
        $("#kpis-captura").innerHTML =
          kpi(`Oportunidad si se capta el ${(t * 100).toFixed(0)}%`,
              cop(c.entrada_bruta_12m * t),
              "dinero que podría entrar × tasa de captura") +
          kpi("Escenario conservador · 10%", cop(c.entrada_bruta_12m * 0.10)) +
          kpi("Escenario base · 25%", cop(c.entrada_bruta_12m * 0.25)) +
          kpi("Escenario optimista · 40%", cop(c.entrada_bruta_12m * 0.40));
      };
      slider.addEventListener("input", pintar);
      pintar();

      const dim = await api("/api/dimensionamiento");
      const suma = (k) => dim.reduce((a, f) => a + (f[k] || 0), 0);
      tabla($("#tabla-componentes"),
        [{ titulo: "Origen", campo: "o" }, { titulo: "Monto", campo: "m", clase: "num" },
         { titulo: "Qué significa", campo: "s" }],
        [{ o: "Invesbot e Inversión Virtual", m: suma("monto_app_base"),
           s: "Negocio nuevo: más inversión digital" },
         { o: "CDT y Fiducuenta", m: suma("monto_prod_conservadores_base"),
           s: "Traslado: plata que ya está en el banco" }],
        { m: (v) => esc(cop(v)) });
    } catch (e) { fallo($("#kpis-oportunidad"), e); }
  },

  async contactar() {
    try {
      const d = await datosResumen();
      const base = d.cifras.tasa_adopcion;
      tabla($("#tabla-curva"),
        [{ titulo: "Se contacta", campo: "top_pct" },
         { titulo: "Llamadas", campo: "n_contactados", clase: "num" },
         { titulo: "De cada 100, aciertan", campo: "precision_", clase: "num" },
         { titulo: "Alcance", campo: "recall_", clase: "num" },
         { titulo: "Mejor que azar", campo: "lift", clase: "num" }],
        d.curva.map((f) => ({ ...f, lift: f.precision_ / base })),
        { top_pct: (v) => `Top ${pct(v, 0)}`,
          n_contactados: (v) => miles(v),
          precision_: (v) => pct(v, 0),
          recall_: (v) => pct(v, 0),
          lift: (v) => `${v.toFixed(1)}×` });

      await montarFiltros();
      $("#btn-buscar").addEventListener("click", buscarCliente);
      $("#busca-cliente").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") buscarCliente();
      });
    } catch (e) { fallo($("#tabla-curva"), e); }
  },

  async supuestos() {
    try {
      const s = await api("/api/sesgo");
      tabla($("#tabla-sesgo"),
        [{ titulo: "Atributo", campo: "atributo" }, { titulo: "Grupo", campo: "grupo" },
         { titulo: "Clientes", campo: "n", clase: "num" },
         { titulo: "En nivel A", campo: "n_seleccionados", clase: "num" },
         { titulo: "Tasa de selección", campo: "tasa_seleccion_nivel_A", clase: "num" },
         { titulo: "Razón", campo: "razon_impacto_dispar", clase: "num" }],
        s,
        { n: (v) => miles(v), n_seleccionados: (v) => miles(v),
          tasa_seleccion_nivel_A: (v) => pct(v),
          razon_impacto_dispar: (v) => Number(v).toFixed(2) });
    } catch (e) { fallo($("#tabla-sesgo"), e); }
  },
};

// ------------------------------------------------------- lista de contacto
let LISTA_ACTUAL = [];

async function montarFiltros() {
  const f = await api("/api/facetas");
  const sel = (id, etq, ops, marcados) =>
    `<label>${etq}<select id="${id}" multiple size="4">` +
    ops.map((o) => `<option value="${esc(o)}"${marcados.includes(o) ? " selected" : ""}>${esc(o)}</option>`).join("") +
    `</select></label>`;

  $("#filtros-lista").innerHTML =
    sel("f-poblacion", "Grupo de clientes", f.poblaciones, f.poblaciones) +
    sel("f-nivel", "Nivel", f.niveles, ["A"]) +
    sel("f-segmento", "Segmento", f.segmentos, f.segmentos) +
    `<label>Cuántas filas<input type="number" id="f-limite" value="100" min="10" max="500" step="10"></label>` +
    `<label class="check"><input type="checkbox" id="f-con-monto">Solo con monto estimado</label>` +
    `<button class="accion" id="btn-lista">Aplicar</button>` +
    `<button class="accion secundaria" id="btn-csv" type="button">Descargar CSV</button>`;

  $("#btn-lista").addEventListener("click", cargarLista);
  $("#btn-csv").addEventListener("click", descargarLista);
  await cargarLista();
}

const elegidos = (id) =>
  Array.from($(id).selectedOptions).map((o) => o.value);

async function cargarLista() {
  const p = new URLSearchParams();
  for (const [campo, id] of [["poblacion", "#f-poblacion"], ["nivel", "#f-nivel"],
                             ["segmento", "#f-segmento"]]) {
    const vs = elegidos(id);
    if (vs.length) p.set(campo, vs.join(","));
  }
  p.set("limit", $("#f-limite").value || "100");
  if ($("#f-con-monto")?.checked) p.set("con_monto", "1");

  $("#pie-lista").textContent = "Consultando…";
  try {
    const d = await api(`/api/clientes?${p}`);
    LISTA_ACTUAL = d.filas;
    $("#kpis-lista").innerHTML =
      kpi("Clientes que cumplen", miles(d.total)) +
      kpi("Dinero que podrían mover", cop(d.entrada_bruta)) +
      kpi("Mostrando", miles(d.filas.length), `tope de ${d.limite} por consulta`);

    tabla($("#tabla-clientes"),
      [{ titulo: "ID cliente", campo: "numero_id", clase: "id" },
       { titulo: "Grupo", campo: "poblacion" }, { titulo: "Nivel", campo: "nivel" },
       { titulo: "Segmento", campo: "desc_segmento" },
       { titulo: "Edad", campo: "grupo_edad" },
       { titulo: "Puntaje", campo: "score", clase: "num" },
       { titulo: "Posición en su grupo", campo: "percentil_en_grupo", clase: "num" },
       { titulo: "Monto 12m", campo: "monto_base_12m", clase: "num" }],
      d.filas,
      { numero_id: (v) => `<button class="id-boton" data-id="${esc(v)}">${esc(v)}</button>`,
        score: (v) => Number(v).toFixed(4),
        percentil_en_grupo: (v) => progresoPct(v),
        monto_base_12m: (v) => esc(cop(v)) });
    document.querySelectorAll(".id-boton").forEach((b) => {
      b.addEventListener("click", () => {
        $("#busca-cliente").value = b.dataset.id;
        buscarCliente();
      });
    });

    $("#pie-lista").textContent =
      `Se ordena por posición dentro de cada grupo, no por el valor crudo: las ` +
      `escalas de los tres grupos no son comparables entre sí.`;
  } catch (e) {
    LISTA_ACTUAL = [];
    fallo($("#tabla-clientes"), e);
    $("#pie-lista").textContent = "";
  }
}

function csvValor(v) {
  if (v === null || v === undefined) return "";
  return `"${String(v).replace(/"/g, '""')}"`;
}

function descargarLista() {
  if (!LISTA_ACTUAL.length) return;
  const columnas = ["numero_id", "poblacion", "nivel", "desc_segmento", "grupo_edad",
    "score", "modelo_usado", "monto_base_12m", "valor_esperado_12m",
    "percentil_en_grupo"];
  const lineas = [
    columnas.join(","),
    ...LISTA_ACTUAL.map((fila) => columnas.map((c) => csvValor(fila[c])).join(",")),
  ];
  const blob = new Blob(["\ufeff" + lineas.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "lista_contacto_crean.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function buscarCliente() {
  const id = $("#busca-cliente").value.trim();
  const destino = $("#ficha-cliente");
  if (!id) { destino.innerHTML = ""; return; }
  destino.innerHTML = `<p class="cargando">Buscando…</p>`;
  try {
    const c = await api(`/api/cliente?id=${encodeURIComponent(id)}`);
    destino.innerHTML =
      `<div class="ficha-grid">` +
      kpi("Puntaje", Number(c.score).toFixed(4), `nivel ${c.nivel}`) +
      kpi("Grupo", String(c.poblacion).replace("_", " ")) +
      kpi("Monto estimado 12m", cop(c.monto_base_12m)) +
      kpi("Valor esperado", cop(c.valor_esperado_12m)) +
      kpi("Segmento", c.desc_segmento ?? "—") +
      kpi("Edad", c.grupo_edad ?? "—") +
      kpi("Modelo usado", c.modelo_usado ?? "—") +
      kpi("Posición en su grupo", pct(c.percentil_en_grupo, 2)) +
      `</div>
      <div class="cautela">El puntaje ordena, no promete. En el grupo sin
      productos mide <b>parecido</b> con quienes invierten, no una probabilidad
      validada.</div>`;
  } catch (e) {
    destino.innerHTML = `<div class="error">No se encontró un cliente con ese
      identificador. Copie uno de la tabla de arriba.</div>`;
  }
}

// ------------------------------------------------------------------ arranque
const inicial = location.hash.replace("#", "") || "resumen";
mostrar(document.getElementById(inicial) ? inicial : "resumen");
