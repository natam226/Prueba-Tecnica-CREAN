# oro/construir_esquema_estrella.py
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

TABLAS_PRODUCTO_LARGAS = [
    "aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
    "cdt_inversion_virtual_plata", "invesbot_plata",
]


def construir_esquema_estrella():
    clientes = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")
    # SPEC_V2 §8: dim_cliente incluye desc_genero SOLO para auditoría de sesgo y
    # caracterización descriptiva del tablero. Nunca como predictora.
    cols_dim = ["numero_id", "grupo_edad", "desc_genero", "desc_segmento",
                "desc_tipo_de_vivienda"]
    dim_cliente = clientes[[c for c in cols_dim if c in clientes.columns]]
    escribir_tabla_sqlite(dim_cliente, config.ORO_DB, "dim_cliente")

    # --- fact_saldos_mensual: grano MENSUAL (SPEC_V2 §8) ---
    mensual = leer_tabla_sqlite(config.PLATA_DB, "saldos_mensual_plata")
    mensual["mes"] = pd.to_datetime(mensual["mes"])

    dim_producto = pd.DataFrame({"producto": sorted(mensual["producto"].unique())})
    dim_producto["producto_id"] = range(1, len(dim_producto) + 1)
    escribir_tabla_sqlite(dim_producto, config.ORO_DB, "dim_producto")

    dim_tiempo = (
        mensual[["mes"]].drop_duplicates().sort_values("mes")
        .rename(columns={"mes": "fecha"}).reset_index(drop=True)
    )
    dim_tiempo["fecha_id"] = range(1, len(dim_tiempo) + 1)
    dim_tiempo["anio"] = dim_tiempo["fecha"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha"].dt.month
    dim_tiempo["trimestre"] = dim_tiempo["fecha"].dt.quarter
    escribir_tabla_sqlite(dim_tiempo, config.ORO_DB, "dim_tiempo")

    fact_saldos_mensual = (
        mensual
        .merge(dim_producto, on="producto", how="left")
        .merge(dim_tiempo[["fecha", "fecha_id"]], left_on="mes", right_on="fecha",
               how="left")
        [["numero_id", "producto_id", "fecha_id", "mes", "saldo_mes"]]
    )
    escribir_tabla_sqlite(fact_saldos_mensual, config.ORO_DB, "fact_saldos_mensual")

    # fact_saldos (snapshot cliente-producto) se conserva: alimenta las vistas
    # de "último saldo" del tablero, que no necesitan la serie mensual completa.
    fact_frames = [leer_tabla_sqlite(config.PLATA_DB, t) for t in TABLAS_PRODUCTO_LARGAS]
    fact_saldos = pd.concat(fact_frames, ignore_index=True)
    if not fact_saldos.empty:
        fact_saldos["fecha_snapshot"] = pd.to_datetime(fact_saldos["fecha_snapshot"])
        fact_saldos = fact_saldos.merge(dim_producto, on="producto", how="left")
    escribir_tabla_sqlite(fact_saldos, config.ORO_DB, "fact_saldos")

    return dim_cliente, dim_producto, dim_tiempo, fact_saldos_mensual


if __name__ == "__main__":
    dim_cliente, dim_producto, dim_tiempo, fact_mensual = construir_esquema_estrella()
    print(f"dim_cliente: {len(dim_cliente):,} | dim_producto: {len(dim_producto)} | "
          f"dim_tiempo: {len(dim_tiempo)} meses")
    print(f"fact_saldos_mensual: {len(fact_mensual):,} filas (grano mensual)")
