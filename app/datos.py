"""Carga cacheada de los artefactos que produce el pipeline.

El tablero NO recalcula nada: si una cifra de aquí no cuadra con un notebook,
el notebook manda. Deliberadamente no se carga `fact_saldos_mensual`
(9.9 M filas): la serie mensual se agrega en el pipeline, no aquí.
"""
import json
import sqlite3
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


def resumen_ejecutivo() -> dict:
    return jsonf("eda/resumen_ejecutivo.json")


def metricas_propension() -> dict:
    return jsonf("models/metricas_propension.json")


def tasa_base() -> float:
    """Proporción de adoptantes en la base apta. Es la referencia contra la
    que se lee cualquier otra tasa del tablero."""
    return metricas_propension()["tasa_adopcion"]


@st.cache_data
def features_de(numero_id: str) -> pd.Series | None:
    """Fila de `cliente_features` de un cliente, para la ficha individual.

    Es la única lectura del tablero que va a `oro.db` en vez de a `outputs/`:
    los valores crudos por cliente no están en ningún entregable, y exportar
    860.223 filas por 90 columnas para consultar una sola sería peor.

    `numero_id` entra y se compara como TEXTO porque llega a ±9.2e18 y
    convertirlo a número le cambiaría los últimos dígitos.
    """
    if not config.ORO_DB.exists():
        raise ArtefactosFaltantes("oro/data/oro.db")
    con = sqlite3.connect(config.ORO_DB)
    try:
        fila = pd.read_sql(
            "SELECT * FROM cliente_features WHERE CAST(numero_id AS TEXT) = ?",
            con, params=(str(numero_id),))
    finally:
        con.close()
    if fila.empty:
        return None
    return fila.iloc[0]


@st.cache_data
def medianas_por_etiqueta(variables: tuple[str, ...]) -> pd.DataFrame:
    """Mediana de cada variable entre adoptantes y no adoptantes.

    Es el contraste que convierte un valor suelto en información: saber que un
    cliente tiene $24 M de patrimonio no dice nada hasta verlo al lado de la
    mediana de quien adopta.
    """
    if not config.ORO_DB.exists():
        raise ArtefactosFaltantes("oro/data/oro.db")
    seleccion = ", ".join(f'"{v}"' for v in variables)
    con = sqlite3.connect(config.ORO_DB)
    try:
        datos = pd.read_sql(
            f"SELECT etiqueta_adopcion, {seleccion} FROM cliente_features", con)
    finally:
        con.close()
    numericas = [v for v in variables
                 if pd.api.types.is_numeric_dtype(datos[v])]
    medianas = datos.groupby("etiqueta_adopcion")[numericas].median().T
    medianas.columns = [f"mediana_{'adoptantes' if c == 1 else 'no_adoptantes'}"
                        for c in medianas.columns]
    return medianas.reset_index(names="variable")


# Qué hay que ejecutar para producir cada artefacto. Sin este mapa el aviso
# diría "falta un archivo" y dejaría al lector adivinando cuál de los diez
# pasos del pipeline se saltó.
PRODUCTOR = {
    "eda/resumen_shape.json": "notebooks/01_eda.ipynb",
    "eda/tasas_adopcion_por_segmento.csv": "notebooks/01_eda.ipynb",
    "eda/faltantes_tasa_adopcion.csv": "notebooks/03_eda_faltantes.ipynb",
    "eda/validacion_variables.csv": "notebooks/04_validacion_variables.ipynb",
    "eda/resumen_ejecutivo.json": "notebooks/05_dimensionamiento.ipynb",
    "models/metricas_propension.json": "notebooks/02_modelado.ipynb",
    "models/curva_precision_recall.csv": "notebooks/02_modelado.ipynb",
    "powerbi/dimensionamiento.csv": "notebooks/05_dimensionamiento.ipynb",
    "powerbi/fact_auditoria_sesgo.csv": "notebooks/07_auditoria_sesgo.ipynb",
    "powerbi/fact_cliente_score.csv": "scripts/export_powerbi.py",
    "powerbi/dim_cliente.csv": "scripts/export_powerbi.py",
    "powerbi/fact_importancia_variables.csv": "scripts/export_powerbi.py",
    "decisiones/log_decisiones.csv": "cualquier notebook del pipeline",
}


def _quien_lo_produce(ruta: str) -> str:
    return PRODUCTOR.get(ruta, "algún paso del pipeline (ver el README)")


def aviso_faltan_artefactos(error: Exception) -> None:
    """El tablero no puede arrancar: falta algo que necesitan todas las vistas."""
    ruta = str(error)
    st.error(
        f"**El pipeline no ha corrido todavía.**\n\n"
        f"Falta `{ruta}`, que produce `{_quien_lo_produce(ruta)}`.\n\n"
        "Ejecutar en orden: `python scripts/run_pipeline.py`, los notebooks "
        "01 a 07 según el README, y `python scripts/export_powerbi.py`."
    )
    st.stop()


def aviso_vista_incompleta(error: Exception, vista: str) -> None:
    """Falta un artefacto de UNA vista: el resto del tablero sigue sirviendo.

    Un paso del pipeline saltado no debe tumbar el tablero entero con un
    traceback de Python: la vista afectada dice qué le falta y las demás
    siguen funcionando.
    """
    ruta = str(error)
    st.warning(
        f"**La vista «{vista}» necesita un artefacto que aún no existe.**\n\n"
        f"Falta `{ruta}`, que produce `{_quien_lo_produce(ruta)}`.\n\n"
        "Las demás vistas del tablero no dependen de este archivo y siguen "
        "disponibles en el menú de la izquierda."
    )
    st.stop()
