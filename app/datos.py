"""Carga cacheada de los artefactos que produce el pipeline.

El tablero NO recalcula nada: si una cifra de aquí no cuadra con un notebook,
el notebook manda. Deliberadamente no se carga `fact_saldos_mensual`
(9.9 M filas): la serie mensual se agrega en el pipeline, no aquí.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


class ArtefactosFaltantes(Exception):
    """El pipeline no ha corrido, o corrió a medias."""


@st.cache_data
def csv(ruta_relativa: str) -> pd.DataFrame:
    ruta = config.OUTPUTS_DIR / ruta_relativa
    if not ruta.exists():
        raise ArtefactosFaltantes(ruta_relativa)
    return pd.read_csv(ruta)


@st.cache_data
def jsonf(ruta_relativa: str) -> dict:
    ruta = config.OUTPUTS_DIR / ruta_relativa
    if not ruta.exists():
        raise ArtefactosFaltantes(ruta_relativa)
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def base_clientes() -> pd.DataFrame:
    """Score por cliente + demografía: lo que consume la lista de contacto.

    `numero_id` se fuerza a texto. Es un entero de 19 dígitos (hasta ±9.2e18),
    muy por encima del entero exacto de float64, así que cualquier herramienta
    que lo infiera como decimal —Excel al abrir el CSV, entre otras— le cambia
    los últimos dígitos en silencio y produce identificadores que no existen.
    """
    score = csv("powerbi/fact_cliente_score.csv")
    dim = csv("powerbi/dim_cliente.csv")
    cols = [c for c in ["numero_id", "desc_segmento", "grupo_edad",
                        "desc_tipo_de_vivienda"] if c in dim.columns]
    datos = score.merge(dim[cols], on="numero_id", how="left")
    datos["numero_id"] = datos["numero_id"].astype("int64").astype(str)
    return datos


def aviso_faltan_artefactos(error: Exception) -> None:
    st.error(
        f"Falta un artefacto del pipeline: `{error}`\n\n"
        "Ejecutar en orden: `python scripts/run_pipeline.py`, los notebooks "
        "01 a 07 según el README, y `python scripts/export_powerbi.py`."
    )
    st.stop()
