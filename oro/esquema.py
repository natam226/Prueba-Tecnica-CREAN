"""Esquema declarado de la capa oro: llaves, restricciones e índices.

POR QUÉ EXISTE ESTE MÓDULO
--------------------------
`pandas.to_sql` crea tablas sin ninguna restricción: sin llave primaria, sin
foránea, sin NOT NULL y sin índices. Durante buena parte del proyecto la
integridad de oro se sostuvo solo en las pruebas automáticas — funcionaba, pero
nada impedía que una corrida metiera un `numero_id` duplicado o un
`producto_id` inexistente y que el error apareciera semanas después como una
cifra rara.

Aquí el esquema se declara y la base lo hace cumplir.

POR QUÉ SE GENERA EL DDL EN VEZ DE ESCRIBIRLO A MANO
----------------------------------------------------
`cliente_features` tiene 90 columnas y crece cada vez que se añade una variable
derivada. Un DDL escrito a mano se desincronizaría en la primera adición. Se
generan los tipos desde el DataFrame y se inyectan solo las restricciones, que
sí son estables.

SOBRE LAS LLAVES FORÁNEAS
-------------------------
SQLite no las verifica salvo que se active `PRAGMA foreign_keys = ON` por
conexión, cosa que hace `escribir_esquema_estrella`. Solo se declaran dentro
del esquema estrella, que se escribe entero en una sola función y en orden de
dependencia. `fact_cliente_score` no lleva foránea a `dim_cliente` a propósito:
las escriben pasos distintos del pipeline y acoplarlas haría que el orden de
ejecución fuera aún más frágil de lo que ya es.
"""
import pandas as pd

# pandas -> SQLite. La afinidad de tipos de SQLite es laxa, pero declararla
# documenta la intención y hace que un valor imposible falle al insertarse.
#
# La coincidencia es por PREFIJO, no exacta: pandas 3 nombra las fechas
# `datetime64[us]` donde pandas 2 usaba `datetime64[ns]`, y una tabla de
# equivalencias exacta las mandaba a TEXT sin avisar. Lo mismo vale para los
# enteros y flotantes de distinta anchura.
_TIPOS = (
    ("datetime64", "TIMESTAMP"),
    ("int", "INTEGER"),
    ("Int", "INTEGER"),
    ("uint", "INTEGER"),
    ("float", "REAL"),
    ("Float", "REAL"),
    ("bool", "INTEGER"),
)


def _tipo_sql(serie: pd.Series) -> str:
    dtype = str(serie.dtype)
    for prefijo, sql in _TIPOS:
        if dtype.startswith(prefijo):
            return sql
    return "TEXT"


def ddl(datos: pd.DataFrame, tabla: str, *, pk=(), no_nulos=(), unicas=(),
        fks=()) -> str:
    """DDL de `tabla` con los tipos de `datos` y las restricciones indicadas.

    `pk` puede ser una columna o varias (llave compuesta). `fks` es una lista
    de tuplas (columna, tabla_destino, columna_destino).
    """
    pk = [pk] if isinstance(pk, str) else list(pk)
    no_nulos = set(no_nulos) | set(pk)   # una llave primaria nunca es nula

    lineas = []
    for col in datos.columns:
        pieza = f'  "{col}" {_tipo_sql(datos[col])}'
        if col in no_nulos:
            pieza += " NOT NULL"
        if col in unicas:
            pieza += " UNIQUE"
        lineas.append(pieza)

    if len(pk) == 1:
        # Se declara en línea para que SQLite la trate como rowid alias.
        lineas = [
            l.replace(f'"{pk[0]}" INTEGER', f'"{pk[0]}" INTEGER PRIMARY KEY')
            if l.strip().startswith(f'"{pk[0]}"') else l
            for l in lineas
        ]
        if not any("PRIMARY KEY" in l for l in lineas):
            lineas.append(f'  PRIMARY KEY ("{pk[0]}")')
    elif pk:
        lineas.append("  PRIMARY KEY (" + ", ".join(f'"{c}"' for c in pk) + ")")

    for columna, destino, col_destino in fks:
        lineas.append(
            f'  FOREIGN KEY ("{columna}") REFERENCES "{destino}" ("{col_destino}")')

    return f'CREATE TABLE "{tabla}" (\n' + ",\n".join(lineas) + "\n);"


# --- Restricciones por tabla ------------------------------------------------
# Lo que NO puede cambiar sin que algo se rompa río abajo.

RESTRICCIONES = {
    "dim_cliente": dict(pk="numero_id"),
    "dim_producto": dict(pk="producto_id", no_nulos=["producto"],
                         unicas=["producto"]),
    "dim_tiempo": dict(pk="fecha_id", no_nulos=["fecha", "anio", "mes"],
                       unicas=["fecha"]),
    "fact_saldos_mensual": dict(
        pk=["numero_id", "producto_id", "mes"],
        # `fecha_id` va NOT NULL porque toda fila debe caer en un mes de
        # dim_tiempo: una foránea en SQLite acepta NULL, así que sin esto un
        # hecho huérfano de tiempo pasaría la verificación.
        no_nulos=["saldo_mes", "fecha_id"],
        fks=[("numero_id", "dim_cliente", "numero_id"),
             ("producto_id", "dim_producto", "producto_id"),
             ("fecha_id", "dim_tiempo", "fecha_id")]),
    # 90 columnas, de las cuales solo la llave y la etiqueta son innegociables.
    "cliente_features": dict(pk="numero_id",
                             no_nulos=["etiqueta_adopcion", "apto_entrenamiento"]),
    "fact_cliente_score": dict(pk="numero_id", no_nulos=["score", "nivel",
                                                         "poblacion"]),
}

# Índices que sostienen las consultas reales, no todas las que se puedan
# imaginar. Un índice que nadie usa solo hace más lenta la escritura.
INDICES = {
    "fact_saldos_mensual": [
        'CREATE INDEX IF NOT EXISTS idx_fsm_cliente ON "fact_saldos_mensual" ("numero_id")',
        'CREATE INDEX IF NOT EXISTS idx_fsm_mes ON "fact_saldos_mensual" ("mes")',
    ],
    "fact_cliente_score": [
        'CREATE INDEX IF NOT EXISTS idx_fcs_poblacion_nivel '
        'ON "fact_cliente_score" ("poblacion", "nivel")',
    ],
}


def ddl_de(datos: pd.DataFrame, tabla: str) -> str | None:
    """DDL de una tabla conocida, o None si no tiene restricciones declaradas."""
    if tabla not in RESTRICCIONES:
        return None
    return ddl(datos, tabla, **RESTRICCIONES[tabla])
