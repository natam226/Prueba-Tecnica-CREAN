"""Carga `seed/` en un SQLite local y ejecuta las consultas del Worker.

    python cloudflare/scripts/verificar_seed.py

D1 *es* SQLite, así que todo lo que se puede romper en el volcado —sintaxis
del SQL, tipos, índices, identificadores truncados— se rompe igual aquí, sin
necesidad de una cuenta de Cloudflare. Lo que esto **no** cubre es el
despliegue en sí, los tiempos de importación remota y el binding de assets.

Se debe correr después de cada `generar_seed.py`: el volcado se queda viejo en
silencio si el pipeline se vuelve a ejecutar.
"""
import math
import re
import sqlite3
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed"
REPLICA = Path(__file__).resolve().parents[1] / "verificacion.db"

TOTAL_ESPERADO = 860_223
TOPE_LISTA = 500

fallos = []


def comprobar(condicion, descripcion, detalle=""):
    marca = "ok  " if condicion else "FALLA"
    print(f"  [{marca}] {descripcion}{f' -- {detalle}' if detalle else ''}")
    if not condicion:
        fallos.append(descripcion)


def cargar() -> sqlite3.Connection:
    """Reconstruye la réplica desde cero con los mismos archivos que van a D1."""
    REPLICA.unlink(missing_ok=True)
    con = sqlite3.connect(REPLICA)

    archivos = [SEED / "schema.sql", SEED / "catalogos.sql"]
    archivos += sorted(SEED.glob("clientes_*.sql"))
    if len(archivos) < 3:
        sys.exit(f"Falta el volcado en {SEED}. Corre antes generar_seed.py")

    for archivo in archivos:
        con.executescript(archivo.read_text(encoding="utf-8"))
        print(f"  cargado {archivo.name}")
    con.commit()
    return con


def main():
    print("Cargando el volcado en una réplica local")
    con = cargar()
    cur = con.cursor()

    print("\nConteos")
    n = cur.execute("SELECT COUNT(*) FROM cliente").fetchone()[0]
    comprobar(n == TOTAL_ESPERADO, "cliente tiene 860.223 filas", f"{n:,}")
    for tabla in ("conteo", "dimensionamiento", "validacion", "curva_esfuerzo",
                  "sesgo", "importancia", "resumen", "tasa_segmento", "woe"):
        m = cur.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        comprobar(m > 0, f"{tabla} no está vacía", f"{m:,} filas")

    print("\nIdentificadores")
    distintos = cur.execute("SELECT COUNT(DISTINCT numero_id) FROM cliente").fetchone()[0]
    comprobar(distintos == n, "numero_id es único", f"{distintos:,}")
    tipos = [t for (t,) in cur.execute(
        "SELECT DISTINCT typeof(numero_id) FROM cliente")]
    comprobar(tipos == ["text"], "numero_id se guardó como texto", str(tipos))

    # El motivo por el que se guarda como texto: si en algún punto hubiera
    # pasado por un float, los identificadores grandes habrían perdido los
    # últimos dígitos. Se comprueba que ninguno quedó con forma de número
    # convertido y que los grandes sobrevivieron intactos.
    raros = cur.execute(
        "SELECT COUNT(*) FROM cliente WHERE numero_id LIKE '%.%' "
        "OR numero_id LIKE '%e%' OR numero_id LIKE '%E%'").fetchone()[0]
    comprobar(raros == 0, "ningún numero_id quedó en notación decimal o científica")

    grandes = cur.execute(
        "SELECT COUNT(*) FROM cliente WHERE LENGTH(numero_id) > 15").fetchone()[0]
    print(f"         ({grandes:,} identificadores exceden el entero exacto de JS)")

    patron = re.compile(r"^-?\d{1,20}$")
    muestra = [i for (i,) in cur.execute(
        "SELECT numero_id FROM cliente ORDER BY LENGTH(numero_id) DESC LIMIT 2000")]
    comprobar(all(patron.match(i) for i in muestra),
              "los identificadores más largos pasan la validación del Worker")

    print("\nCoherencia de los totales precalculados")
    # `conteo` existe para no contar sobre `cliente` en cada carga de página.
    # Si sus totales no cuadran, la web muestra cifras inventadas.
    real = cur.execute("SELECT COUNT(*), SUM(con_inversion) FROM cliente").fetchone()
    pre = cur.execute("SELECT SUM(n), SUM(n_con_inversion) FROM conteo").fetchone()
    comprobar(real[0] == pre[0], "SUM(conteo.n) == COUNT(cliente)",
              f"{pre[0]:,} vs {real[0]:,}")
    comprobar(real[1] == pre[1], "SUM(conteo.n_con_inversion) coincide",
              f"{pre[1]:,} vs {real[1]:,}")

    # Y por combinación, no solo en el total: dos errores podrían cancelarse.
    descuadres = cur.execute("""
        SELECT COUNT(*) FROM (
          SELECT c.poblacion, c.nivel, c.desc_segmento, COUNT(*) AS n
          FROM cliente c GROUP BY 1, 2, 3
        ) r
        JOIN conteo k
          ON k.poblacion = r.poblacion AND k.nivel = r.nivel
         AND IFNULL(k.desc_segmento, '') = IFNULL(r.desc_segmento, '')
        WHERE k.n != r.n
    """).fetchone()[0]
    comprobar(descuadres == 0, "cada combinación de conteo cuadra con cliente")

    print("\nÍndices y plan de consulta")
    # `INDEXED BY` no es una sugerencia: si SQLite no puede usar ese índice,
    # falla la consulta. Que estas dos corran ya demuestra que ambos sirven.
    for indice in ("idx_cliente_percentil", "idx_cliente_filtro"):
        try:
            cur.execute(
                f"SELECT numero_id FROM cliente INDEXED BY {indice} "
                "WHERE poblacion = 'con_historial' AND nivel = 'A' "
                "ORDER BY percentil_en_grupo DESC LIMIT 5").fetchall()
            comprobar(True, f"{indice} es utilizable por el planificador")
        except sqlite3.OperationalError as e:
            comprobar(False, f"{indice} es utilizable por el planificador", str(e))

    print("\nLa regla de selectividad del Worker")
    # total > sqrt(N x limite) decide entre recorrer el índice de percentil o
    # filtrar y ordenar. Se comprueba que elige el camino barato en ambos
    # extremos, con los datos reales.
    # Los valores van en minúscula, como están en la base. Escribirlos en
    # mayúscula haría que cada caso devolviera cero filas y la comprobación
    # pasaría sin comprobar nada.
    casos = [
        ("nivel A", "nivel = 'A'"),
        ("nivel A preferencial", "nivel = 'A' AND desc_segmento = 'preferencial'"),
        ("D preferencial sin historial",
         "nivel = 'D' AND desc_segmento = 'preferencial' "
         "AND poblacion = 'sin_historial'"),
    ]
    limite = 100
    umbral = math.sqrt(TOTAL_ESPERADO * limite)
    for nombre, donde in casos:
        total = cur.execute(
            f"SELECT COUNT(*) FROM cliente WHERE {donde}").fetchone()[0]
        # Un caso que no devuelve nada no prueba nada: se marca como fallo.
        comprobar(total > 0, f"{nombre}: el caso de prueba tiene filas",
                  f"{total:,}")
        if total == 0:
            continue
        recorre = total > umbral
        # Coste aproximado de cada camino, en filas leídas. El recorrido se
        # topa con el tamaño de la tabla: no se pueden leer más filas de las
        # que hay, aunque la fórmula lo sugiera.
        coste_recorrido = min(TOTAL_ESPERADO * limite / total, TOTAL_ESPERADO)
        elegido = coste_recorrido if recorre else total
        alternativo = total if recorre else coste_recorrido
        comprobar(elegido <= alternativo,
                  f"{nombre}: elige el camino barato",
                  f"{total:,} coinciden -> "
                  f"{'recorrido' if recorre else 'filtro'} "
                  f"({elegido:,.0f} filas vs {alternativo:,.0f})")

    print("\nConsultas del Worker")
    rutas = {
        "/api/resumen": "SELECT clave, valor FROM resumen",
        "/api/dimensionamiento":
            "SELECT * FROM dimensionamiento ORDER BY nivel, poblacion, desc_segmento",
        "/api/validacion": "SELECT * FROM validacion ORDER BY iv DESC",
        "/api/sesgo": "SELECT * FROM sesgo",
        "/api/importancia":
            "SELECT variable, importancia, iv, decision_inclusion FROM importancia "
            "WHERE modelo = 'A' ORDER BY importancia DESC LIMIT 15",
        "/api/facetas":
            "SELECT DISTINCT desc_segmento FROM cliente "
            "WHERE desc_segmento IS NOT NULL ORDER BY desc_segmento",
        "/api/clientes":
            "SELECT numero_id, poblacion, nivel, desc_segmento, grupo_edad, score, "
            "modelo_usado, monto_base_12m, valor_esperado_12m, percentil_en_grupo "
            "FROM cliente INDEXED BY idx_cliente_percentil WHERE nivel IN ('A') "
            f"ORDER BY percentil_en_grupo DESC LIMIT {TOPE_LISTA}",
    }
    for ruta, sql in rutas.items():
        try:
            filas = cur.execute(sql).fetchall()
            comprobar(len(filas) > 0, f"{ruta} devuelve filas", f"{len(filas):,}")
        except sqlite3.Error as e:
            comprobar(False, f"{ruta} devuelve filas", str(e))

    # La ficha individual, con un identificador real tomado de la propia tabla.
    uno = cur.execute("SELECT numero_id FROM cliente LIMIT 1").fetchone()[0]
    fila = cur.execute(
        "SELECT numero_id FROM cliente WHERE numero_id = ?", (uno,)).fetchone()
    comprobar(fila is not None, "/api/cliente encuentra por identificador", uno)

    print("\nCifras publicadas")
    cifras = dict(cur.execute("SELECT clave, valor FROM resumen"))
    for clave, esperado, tol in [
        ("auc_modelo_a", 0.8933, 5e-4),
        ("auc_modelo_b", 0.8338, 5e-4),
        ("n_clientes_total", 860_223, 0),
        ("n_nivel_A", 215_057, 0),
        ("entrada_bruta_12m", 1_859_309_351_232, 1e6),
        ("n_clientes_con_monto", 219_542, 0),
    ]:
        v = cifras.get(clave)
        comprobar(v is not None and abs(v - esperado) <= tol,
                  f"{clave} coincide con lo publicado", f"{v:,.4f}")

    con.close()
    REPLICA.unlink(missing_ok=True)

    print()
    if fallos:
        print(f"{len(fallos)} comprobaciones fallaron:")
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    print("Todas las comprobaciones pasaron. El volcado está listo para D1.")


if __name__ == "__main__":
    main()
