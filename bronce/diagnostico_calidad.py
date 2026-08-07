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


def verificar_unicidad_producto_fecha(df, nombre_tabla):
    """SPEC_V2 §9.1: (numero_id, producto, fecha) debe ser único.

    Si falta alguna de las tres columnas clave, el chequeo NO puede
    realizarse: se devuelve `unico=None` y `verificado=False` para que
    esto sea distinguible de una verificación real que pasó (`unico=True`).
    Un `unico=True` aquí significaría "no encontré duplicados" incluso
    cuando en realidad no se buscó nada, lo cual sería peor que no reportar.
    """
    claves = ["numero_id", "producto", "fecha"]
    presentes = [c for c in claves if c in df.columns]
    if len(presentes) < 3:
        faltantes = set(claves) - set(presentes)
        return {"tabla": nombre_tabla, "duplicados": 0, "unico": None, "verificado": False,
                "nota": f"no verificado: columnas ausentes: {faltantes}"}
    dup = int(df.duplicated(subset=claves).sum())
    return {"tabla": nombre_tabla, "duplicados": dup, "unico": dup == 0, "verificado": True}


def verificar_unicidad_cliente(df, nombre_tabla):
    """SPEC_V2 §9.2: numero_id único."""
    dup = int(df["numero_id"].duplicated().sum())
    return {"tabla": nombre_tabla, "duplicados": dup, "unico": dup == 0, "verificado": True}


def _estado_granularidad(r):
    if not r.get("verificado", True):
        return f"NO VERIFICADO ({r.get('nota', 'sin detalle')})"
    if r["unico"]:
        return "OK"
    return f"FALLA ({r['duplicados']} duplicados)"


def reporte_granularidad(resultados):
    lineas = ["## Granularidad (SPEC_V2 §9)"]
    for r in resultados:
        lineas.append(f"- {r['tabla']}: {_estado_granularidad(r)}")
    return lineas


def main():
    clientes = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    ids_clientes = set(clientes["numero_id"].unique())

    lineas = ["# Reporte de calidad — bronce", ""]
    lineas += reporte_nulos_clientes(clientes)
    lineas += reporte_duplicados_clientes(clientes)

    granularidad = []
    for tabla in TABLAS_SALDO:
        df = leer_tabla_sqlite(config.BRONCE_DB, tabla)
        lineas += reporte_encoding_producto(tabla, df)
        lineas += reporte_integridad_referencial(tabla, df, ids_clientes)
        granularidad.append(verificar_unicidad_producto_fecha(df, tabla))

    estimador = leer_tabla_sqlite(config.BRONCE_DB, "estimador_ing")
    lineas += reporte_integridad_referencial("estimador_ing", estimador, ids_clientes)
    granularidad.append(verificar_unicidad_cliente(estimador, "estimador_ing"))

    if config.ORO_DB.exists():
        cf = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
        granularidad.append(verificar_unicidad_cliente(cf, "cliente_features"))

    lineas += reporte_granularidad(granularidad)

    salida = config.OUTPUTS_DIR / "quality" / "reporte_calidad.md"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Reporte escrito en {salida}")
    for r in granularidad:
        print(f"  {r['tabla']}: {_estado_granularidad(r)}")


if __name__ == "__main__":
    main()
