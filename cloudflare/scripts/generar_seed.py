"""Genera los archivos .sql que se cargan a Cloudflare D1.

    python cloudflare/scripts/generar_seed.py

Lee `oro.db` y `outputs/` y escribe en `cloudflare/seed/`:

  schema.sql          estructura e índices
  catalogos.sql       las tablas pequeñas (todas juntas, ~600 filas)
  clientes_NNN.sql    la tabla de clientes, en lotes

DECISIONES QUE IMPORTAN
-----------------------
**`numero_id` se guarda como TEXTO.** Llega a ±9,2e18 y todo Worker es
JavaScript, donde el entero exacto máximo es 9,007e15. Guardarlo como número
haría que `JSON.parse` le cambiara los últimos dígitos en silencio y la API
devolvería identificadores que no existen.

**Se precalcula `percentil_en_grupo`.** Rankear dentro de cada población en
tiempo de consulta obligaría a leer la tabla entera en cada petición. D1 factura
por filas leídas (5 millones/día en el plan gratuito) y un solo escaneo consume
el 17% de ese presupuesto.

**Solo viajan las columnas que el tablero web usa.** No es una réplica de
`oro.db`: es la capa de servicio.
"""
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config

SALIDA = Path(__file__).resolve().parents[1] / "seed"
FILAS_POR_LOTE = 500          # filas por sentencia INSERT
FILAS_POR_ARCHIVO = 100_000   # para que ningún archivo sea inmanejable


def sql_valor(v) -> str:
    """Literal SQL seguro. NULL para nulos, comillas escapadas para texto.

    Los infinitos se convierten a NULL. `repr(float('inf'))` es la cadena
    `inf`, que SQLite interpreta como un nombre de columna y hace fallar la
    carga entera. Aparecen en la columna VIF: un VIF infinito significa
    colinealidad perfecta con otra variable, y esa información ya la lleva
    `decision_inclusion` ("incluir_con_alerta_multicolinealidad"), así que no
    se pierde nada al no representar el número.
    """
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not math.isfinite(v):
            return "NULL"
        return repr(v)
    if not isinstance(v, str) and pd.isna(v):
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def inserts(tabla: str, datos: pd.DataFrame) -> str:
    """INSERT por lotes: una sentencia cada FILAS_POR_LOTE filas.

    Una sentencia por fila multiplicaría por seis el tamaño del archivo y el
    tiempo de importación.
    """
    if datos.empty:
        return ""
    columnas = ", ".join(f'"{c}"' for c in datos.columns)
    partes = []
    for inicio in range(0, len(datos), FILAS_POR_LOTE):
        lote = datos.iloc[inicio:inicio + FILAS_POR_LOTE]
        valores = ",\n".join(
            "(" + ", ".join(sql_valor(v) for v in fila) + ")"
            for fila in lote.itertuples(index=False, name=None))
        partes.append(f"INSERT INTO {tabla} ({columnas}) VALUES\n{valores};")
    return "\n".join(partes) + "\n"


ESQUEMA = """
DROP TABLE IF EXISTS cliente;
DROP TABLE IF EXISTS dimensionamiento;
DROP TABLE IF EXISTS validacion;
DROP TABLE IF EXISTS curva_esfuerzo;
DROP TABLE IF EXISTS sesgo;
DROP TABLE IF EXISTS importancia;
DROP TABLE IF EXISTS resumen;
DROP TABLE IF EXISTS tasa_segmento;
DROP TABLE IF EXISTS woe;

-- numero_id es TEXTO a proposito: excede el entero exacto de JavaScript.
CREATE TABLE cliente (
  numero_id            TEXT PRIMARY KEY,
  poblacion            TEXT NOT NULL,
  nivel                TEXT NOT NULL,
  desc_segmento        TEXT,
  grupo_edad           TEXT,
  score                REAL NOT NULL,
  modelo_usado         TEXT,
  monto_base_12m       REAL,
  valor_esperado_12m   REAL,
  percentil_en_grupo   REAL NOT NULL,
  con_inversion        INTEGER NOT NULL
);

-- La lista de contacto filtra por estos tres campos y ordena por percentil.
-- Sin este indice cada consulta escanearia las 860.223 filas.
CREATE INDEX idx_cliente_filtro
  ON cliente (poblacion, nivel, desc_segmento, percentil_en_grupo DESC);
CREATE INDEX idx_cliente_percentil ON cliente (percentil_en_grupo DESC);

-- Conteos precalculados por combinacion de filtro (24 filas como maximo).
-- Sin esta tabla, el total de la lista exigiria un COUNT sobre la tabla de
-- clientes: para "nivel A" serian 215.057 entradas de indice leidas en CADA
-- carga de pagina, y D1 factura por filas leidas.
CREATE TABLE conteo (
  poblacion      TEXT NOT NULL,
  nivel          TEXT NOT NULL,
  desc_segmento  TEXT,
  n              INTEGER NOT NULL,
  n_con_inversion INTEGER NOT NULL,
  entrada_bruta  REAL NOT NULL
);

CREATE TABLE dimensionamiento (
  nivel TEXT, bloque_comercial TEXT, poblacion TEXT, desc_segmento TEXT,
  n_clientes INTEGER, monto_base REAL, monto_entrada_bruta REAL,
  monto_salida_bruta REAL, monto_app_base REAL,
  monto_prod_conservadores_base REAL, score_medio REAL
);

CREATE TABLE validacion (
  variable TEXT, tipo TEXT, iv REAL, clase_iv TEXT,
  q_bh REAL, significativa_fdr TEXT, vif REAL, decision_inclusion TEXT
);

CREATE TABLE curva_esfuerzo (
  top_pct REAL, n_contactados INTEGER, precision_ REAL, recall_ REAL
);

CREATE TABLE sesgo (
  atributo TEXT, grupo TEXT, n INTEGER, n_seleccionados INTEGER,
  tasa_seleccion_nivel_A REAL, razon_impacto_dispar REAL,
  cumple_regla_80 TEXT, auc_proxy_genero REAL, interpretacion_proxy_genero TEXT
);

CREATE TABLE importancia (
  variable TEXT, importancia REAL, modelo TEXT, iv REAL, decision_inclusion TEXT
);

CREATE TABLE tasa_segmento (
  variable TEXT, categoria TEXT, tasa_adopcion REAL, n_clientes INTEGER
);

-- Clave/valor: las cifras del resumen ejecutivo y las metricas del modelo.
CREATE TABLE resumen (clave TEXT PRIMARY KEY, valor REAL);

CREATE TABLE woe (
  variable TEXT, bin TEXT, woe REAL, n INTEGER
);
CREATE INDEX idx_woe_variable ON woe (variable);
"""


def construir_clientes(con) -> pd.DataFrame:
    score = pd.read_sql(
        "SELECT numero_id, poblacion, nivel, score, modelo_usado, "
        "monto_base_12m, valor_esperado_12m, valor_referencia, "
        "tiene_historial_inversion FROM fact_cliente_score", con)
    dim = pd.read_sql(
        "SELECT numero_id, desc_segmento, grupo_edad FROM dim_cliente", con)
    d = score.merge(dim, on="numero_id", how="left")

    d["numero_id"] = d["numero_id"].astype("int64").astype(str)
    # Mismo criterio que el tablero y que src/niveles.py: el ranking vale
    # DENTRO de cada poblacion, porque `valor_referencia` significa cosas
    # distintas en cada una y sus escalas no son comparables.
    d["percentil_en_grupo"] = (
        d.groupby("poblacion")["valor_referencia"].rank(method="first", pct=True))
    d = d.rename(columns={"tiene_historial_inversion": "con_inversion"})
    return d[["numero_id", "poblacion", "nivel", "desc_segmento", "grupo_edad",
              "score", "modelo_usado", "monto_base_12m", "valor_esperado_12m",
              "percentil_en_grupo", "con_inversion"]]


def construir_resumen() -> pd.DataFrame:
    import json

    with open(config.OUTPUTS_DIR / "eda" / "resumen_ejecutivo.json",
              encoding="utf-8") as f:
        ej = json.load(f)
    with open(config.OUTPUTS_DIR / "models" / "metricas_propension.json",
              encoding="utf-8") as f:
        mp = json.load(f)

    filas = {k: v for k, v in ej.items() if isinstance(v, (int, float))}
    filas["auc_modelo_a"] = mp["modelo_a"]["auc"]
    filas["auc_modelo_b"] = mp["modelo_b"]["auc"]
    filas["n_features_a"] = mp["modelo_a"]["n_features"]
    filas["n_features_b"] = mp["modelo_b"]["n_features"]
    filas["tasa_adopcion"] = mp["tasa_adopcion"]
    return pd.DataFrame({"clave": list(filas), "valor": list(filas.values())})


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    for viejo in SALIDA.glob("*.sql"):
        viejo.unlink()

    (SALIDA / "schema.sql").write_text(ESQUEMA.strip() + "\n", encoding="utf-8")
    print(f"schema.sql")

    con = sqlite3.connect(config.ORO_DB)
    try:
        clientes = construir_clientes(con)
    finally:
        con.close()

    conteo = (
        clientes.assign(
            entrada=clientes["monto_base_12m"].clip(lower=0).fillna(0))
        .groupby(["poblacion", "nivel", "desc_segmento"], dropna=False)
        .agg(n=("numero_id", "count"),
             n_con_inversion=("con_inversion", "sum"),
             entrada_bruta=("entrada", "sum"))
        .reset_index()
    )

    # ---- catalogos: todas las tablas pequeñas en un solo archivo ----
    out = config.OUTPUTS_DIR
    dim = pd.read_csv(out / "powerbi" / "dimensionamiento.csv")
    val = pd.read_csv(out / "eda" / "validacion_variables.csv")
    curva = pd.read_csv(out / "models" / "curva_precision_recall.csv").rename(
        columns={"precision": "precision_", "recall": "recall_"})
    ses = pd.read_csv(out / "powerbi" / "fact_auditoria_sesgo.csv")
    imp = pd.read_csv(out / "powerbi" / "fact_importancia_variables.csv")
    tas = pd.read_csv(out / "eda" / "tasas_adopcion_por_segmento.csv")
    woe = pd.read_csv(out / "eda" / "woe_por_bin.csv")

    def recorta(d, cols):
        return d[[c for c in cols if c in d.columns]].astype(object)

    catalogos = "".join([
        inserts("dimensionamiento", recorta(dim, [
            "nivel", "bloque_comercial", "poblacion", "desc_segmento",
            "n_clientes", "monto_base", "monto_entrada_bruta",
            "monto_salida_bruta", "monto_app_base",
            "monto_prod_conservadores_base", "score_medio"])),
        inserts("validacion", recorta(val, [
            "variable", "tipo", "iv", "clase_iv", "q_bh", "significativa_fdr",
            "vif", "decision_inclusion"]).astype({"significativa_fdr": str})),
        inserts("curva_esfuerzo", recorta(curva, [
            "top_pct", "n_contactados", "precision_", "recall_"])),
        inserts("sesgo", recorta(ses, [
            "atributo", "grupo", "n", "n_seleccionados",
            "tasa_seleccion_nivel_A", "razon_impacto_dispar",
            "cumple_regla_80", "auc_proxy_genero",
            "interpretacion_proxy_genero"]).astype({"cumple_regla_80": str})),
        inserts("importancia", recorta(imp, [
            "variable", "importancia", "modelo", "iv", "decision_inclusion"])),
        inserts("tasa_segmento", recorta(tas.dropna(subset=["categoria"]), [
            "variable", "categoria", "tasa_adopcion", "n_clientes"])),
        inserts("resumen", construir_resumen().astype(object)),
        inserts("woe", recorta(woe, ["variable", "bin", "woe", "n"])),
        inserts("conteo", conteo.astype(object)),
    ])
    (SALIDA / "catalogos.sql").write_text(catalogos, encoding="utf-8")
    print(f"catalogos.sql  ({len(catalogos) / 1e6:.1f} MB)")

    # ---- clientes, en trozos ----
    total = 0
    for i, inicio in enumerate(range(0, len(clientes), FILAS_POR_ARCHIVO), 1):
        trozo = clientes.iloc[inicio:inicio + FILAS_POR_ARCHIVO].astype(object)
        texto = inserts("cliente", trozo)
        nombre = f"clientes_{i:03d}.sql"
        (SALIDA / nombre).write_text(texto, encoding="utf-8")
        total += len(texto)
        print(f"{nombre}  ({len(trozo):,} filas, {len(texto) / 1e6:.1f} MB)")

    print(f"\nTotal clientes: {len(clientes):,} filas, {total / 1e6:.1f} MB")
    print(f"Archivos en {SALIDA}")


if __name__ == "__main__":
    main()
