# src/fecha_corte.py
"""Fecha de corte global del pipeline (D4, DECISIONES.md).

D4 CAMBIA la propuesta provisional del plan v1 (corte por fuente): con cortes
por fuente cada cliente queda medido en un momento distinto y los saldos dejan
de ser comparables entre clientes. FECHA_CORTE = min(max_fecha de cada fuente)
es el punto más reciente en el que TODAS las fuentes tienen dato: toda ventana
de 6M, todo snapshot y toda antigüedad se miden contra esa única referencia.

estimador_ing NO participa (N3): no tiene columna `fecha`, no hay nada que cortar.
"""
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite

FUENTES_SALDO_CORTE = (
    "crean_aho_cte", "crean_bolsillos", "crean_fiducuenta",
    "crean_inv_virtual_cdt", "invesbot",
)


def calcular_fecha_corte(bronce_db=None) -> pd.Timestamp:
    bronce_db = bronce_db if bronce_db is not None else config.BRONCE_DB
    maximos = []
    for tabla in FUENTES_SALDO_CORTE:
        fechas = pd.to_datetime(leer_tabla_sqlite(bronce_db, tabla)["fecha"])
        maximos.append(fechas.max())
    return min(maximos)
