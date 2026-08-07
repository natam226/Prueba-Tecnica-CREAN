# bronce/diagnostico_calidad.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.db_io import leer_tabla_sqlite

TABLAS_SALDO = ["crean_aho_cte", "crean_bolsillos", "crean_fiducuenta", "crean_inv_virtual_cdt", "invesbot"]
COLS_FINANCIERAS = config.COLS_FINANCIERAS


def reporte_nulos_clientes(df):
    lineas = ["## Nulos en clientes"]
    for c in COLS_FINANCIERAS + ["desc_genero", "desc_tipo_de_vivienda"]:
        lineas.append(f"- {c}: {df[c].isnull().sum()} nulos")
    return lineas


def reporte_duplicados_clientes(df):
    dup = df["numero_id"].duplicated().sum()
    return [f"## Duplicados en clientes", f"- filas con numero_id repetido: {dup}"]


def reporte_encoding_producto(nombre_tabla, df):
    if "producto" not in df.columns:
        return []
    # Detectar productos con caracteres no-ASCII (p.ej. tildes) — UTF-8 válido, no corrupción de bytes
    sospechosos = df.loc[
        df["producto"].str.contains(r"[^\x00-\x7F]", na=False, regex=True),
        "producto"
    ].unique().tolist()
    return [f"## Anomalías de texto en producto en {nombre_tabla}", f"- valores con caracteres no-ASCII: {sospechosos}"]


def reporte_integridad_referencial(nombre_tabla, df, ids_clientes):
    faltantes = set(df["numero_id"].unique()) - ids_clientes
    return [f"## Integridad referencial {nombre_tabla}", f"- numero_id sin match en clientes: {len(faltantes)}"]


def main():
    clientes = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    ids_clientes = set(clientes["numero_id"].unique())

    lineas = ["# Reporte de calidad — bronce", ""]
    lineas += reporte_nulos_clientes(clientes)
    lineas += reporte_duplicados_clientes(clientes)

    for tabla in TABLAS_SALDO:
        df = leer_tabla_sqlite(config.BRONCE_DB, tabla)
        lineas += reporte_encoding_producto(tabla, df)
        lineas += reporte_integridad_referencial(tabla, df, ids_clientes)

    estimador = leer_tabla_sqlite(config.BRONCE_DB, "estimador_ing")
    lineas += reporte_integridad_referencial("estimador_ing", estimador, ids_clientes)

    salida = config.OUTPUTS_DIR / "quality" / "reporte_calidad.md"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Reporte escrito en {salida}")


if __name__ == "__main__":
    main()
