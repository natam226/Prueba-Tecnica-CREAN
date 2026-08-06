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
    dim_cliente = clientes[["numero_id", "grupo_edad", "desc_genero", "desc_segmento", "desc_tipo_de_vivienda"]]
    escribir_tabla_sqlite(dim_cliente, config.ORO_DB, "dim_cliente")

    fact_frames = [leer_tabla_sqlite(config.PLATA_DB, t) for t in TABLAS_PRODUCTO_LARGAS]
    fact_saldos = pd.concat(fact_frames, ignore_index=True)

    dim_producto = pd.DataFrame({"producto": sorted(fact_saldos["producto"].unique())})
    dim_producto["producto_id"] = range(1, len(dim_producto) + 1)
    escribir_tabla_sqlite(dim_producto, config.ORO_DB, "dim_producto")

    fact_saldos["fecha_snapshot"] = pd.to_datetime(fact_saldos["fecha_snapshot"])
    dim_tiempo = fact_saldos[["fecha_snapshot"]].drop_duplicates().rename(columns={"fecha_snapshot": "fecha"})
    dim_tiempo["anio"] = dim_tiempo["fecha"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha"].dt.month
    dim_tiempo["trimestre"] = dim_tiempo["fecha"].dt.quarter
    escribir_tabla_sqlite(dim_tiempo, config.ORO_DB, "dim_tiempo")

    fact_saldos = fact_saldos.merge(dim_producto, on="producto", how="left")
    escribir_tabla_sqlite(fact_saldos, config.ORO_DB, "fact_saldos")
    return dim_cliente, dim_producto, dim_tiempo, fact_saldos


if __name__ == "__main__":
    dim_cliente, dim_producto, dim_tiempo, fact_saldos = construir_esquema_estrella()
    print(f"dim_cliente: {len(dim_cliente)}, dim_producto: {len(dim_producto)}, "
          f"dim_tiempo: {len(dim_tiempo)}, fact_saldos: {len(fact_saldos)}")
