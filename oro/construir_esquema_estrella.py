"""Esquema estrella de la capa oro, con su esquema declarado.

Produce `dim_cliente`, `dim_producto`, `dim_tiempo` y `fact_saldos_mensual` en
`oro.db`, cada una con llave primaria, NOT NULL, foráneas e índices — ver
`oro/esquema.py`.

Todo se escribe en una sola conexión y en orden de dependencia (dimensiones
antes que hechos) porque las foráneas se verifican: crear el hecho primero
fallaría, y borrar una dimensión con hechos vivos también.

`fact_saldos` (snapshot cliente-producto) existió aquí y se eliminó: no la leía
nadie, no se exportaba, y le faltaba `fecha_id`, así que ni siquiera estaba
enganchada a `dim_tiempo`. El comentario que la justificaba describía unas
vistas de "último saldo" del tablero que nunca se construyeron. El snapshot por
cliente-producto sigue disponible en las tablas de plata.
"""
import sqlite3

import pandas as pd

import config
from oro import esquema
from src.db_io import leer_tabla_sqlite

# De hecho a dimensión: es el orden en que hay que BORRAR. Para crear e
# insertar se recorre al revés.
ORDEN = ["fact_saldos_mensual", "dim_tiempo", "dim_producto", "dim_cliente"]


def construir_tablas() -> dict[str, pd.DataFrame]:
    """Arma los cuatro DataFrames del estrella, sin tocar la base."""
    clientes = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")
    # SPEC_V2 §8: dim_cliente incluye desc_genero SOLO para auditoría de sesgo y
    # caracterización descriptiva del tablero. Nunca como predictora.
    cols_dim = ["numero_id", "grupo_edad", "desc_genero", "desc_segmento",
                "desc_tipo_de_vivienda"]
    dim_cliente = clientes[[c for c in cols_dim if c in clientes.columns]]

    mensual = leer_tabla_sqlite(config.PLATA_DB, "saldos_mensual_plata")
    mensual["mes"] = pd.to_datetime(mensual["mes"])

    dim_producto = pd.DataFrame({"producto": sorted(mensual["producto"].unique())})
    dim_producto["producto_id"] = range(1, len(dim_producto) + 1)

    dim_tiempo = (
        mensual[["mes"]].drop_duplicates().sort_values("mes")
        .rename(columns={"mes": "fecha"}).reset_index(drop=True)
    )
    dim_tiempo["fecha_id"] = range(1, len(dim_tiempo) + 1)
    dim_tiempo["anio"] = dim_tiempo["fecha"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha"].dt.month
    dim_tiempo["trimestre"] = dim_tiempo["fecha"].dt.quarter

    fact = (
        mensual
        .merge(dim_producto, on="producto", how="left")
        .merge(dim_tiempo[["fecha", "fecha_id"]], left_on="mes", right_on="fecha",
               how="left")
        [["numero_id", "producto_id", "fecha_id", "mes", "saldo_mes"]]
    )
    return {"dim_cliente": dim_cliente, "dim_producto": dim_producto,
            "dim_tiempo": dim_tiempo, "fact_saldos_mensual": fact}


def escribir_esquema_estrella(tablas: dict[str, pd.DataFrame]) -> None:
    """Reescribe el estrella completo con las restricciones activas."""
    config.ORO_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.ORO_DB)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        for tabla in ORDEN:                       # hechos primero
            con.execute(f'DROP TABLE IF EXISTS "{tabla}"')
        for tabla in reversed(ORDEN):             # dimensiones primero
            datos = tablas[tabla]
            con.executescript(esquema.ddl_de(datos, tabla))
            datos.to_sql(tabla, con, if_exists="append", index=False)
            for sentencia in esquema.INDICES.get(tabla, []):
                con.execute(sentencia)
        con.commit()
    finally:
        con.close()


def construir_esquema_estrella():
    tablas = construir_tablas()
    escribir_esquema_estrella(tablas)
    return tablas


if __name__ == "__main__":
    t = construir_esquema_estrella()
    print(f"dim_cliente: {len(t['dim_cliente']):,} | "
          f"dim_producto: {len(t['dim_producto'])} | "
          f"dim_tiempo: {len(t['dim_tiempo'])} meses")
    print(f"fact_saldos_mensual: {len(t['fact_saldos_mensual']):,} filas "
          f"(grano mensual, llaves foráneas verificadas)")
