"""Tablero de resultados de la solución analítica de la App de inversiones.

    streamlit run app/tablero.py

Siete vistas en el orden en que se sustenta: qué se hizo, quiénes son los
clientes, qué se construyó, cuánto vale, a quién llamar, qué se asumió y cómo
opera dentro de CREAN.

El público es mixto, así que cada sección abre con la respuesta en lenguaje
llano y guarda el sustento técnico en un cajón plegado. Quien viene del negocio
lee la superficie; quien viene de lo técnico abre el cajón.

Este archivo solo despacha. El contenido vive en `app/paginas/`, el estilo en
`app/estilo.py` y la carga de datos en `app/datos.py`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from app import datos as dat
from app import estilo as es
from app.paginas import (
    clientes, contactar, oportunidad, operacion, resumen, solucion, supuestos,
)

st.set_page_config(page_title="CREAN · App de inversiones",
                   page_icon="📊", layout="wide")
st.markdown(es.CSS, unsafe_allow_html=True)

VISTAS = {
    "Resumen": ("Qué se hizo y para qué", resumen.render),
    "Los clientes": ("Qué distingue a quien invierte", clientes.render),
    "La solución": ("Qué se construyó y qué tan bien funciona", solucion.render),
    "La oportunidad": ("Cuánto dinero puede entrar", oportunidad.render),
    "A quién contactar": ("Cuántas llamadas y a quiénes", contactar.render),
    "Supuestos y sesgos": ("Qué asumimos y qué encontramos", supuestos.render),
    "Cómo opera": ("Datos, procesos CREAN y mantenimiento", operacion.render),
}

with st.sidebar:
    st.markdown("### CREAN · App de inversiones")
    vista = st.radio("Vista", list(VISTAS), label_visibility="collapsed")
    st.caption(VISTAS[vista][0])
    st.divider()
    st.caption(
        "**Lectura rápida:** cada sección abre con la respuesta en lenguaje "
        "llano. El detalle técnico está plegado en los cajones "
        "«detalle técnico»."
    )
    st.caption(
        "**Los niveles no se comparan entre grupos.** Cada A/B/C/D es un "
        "cuartil calculado dentro de su propio grupo de clientes."
    )

# Cada página carga sus propios artefactos. Si falta uno —porque el pipeline
# corrió a medias— el guardián lo convierte en un aviso de esa vista en vez de
# un traceback que tumba el tablero entero.
try:
    VISTAS[vista][1]()
except dat.ArtefactosFaltantes as e:
    dat.aviso_vista_incompleta(e, vista)
