"""Paleta, CSS y formateo compartidos por las vistas del tablero.

Vive aparte de `tablero.py` para que las vistas se lean como contenido y no
como maquetación, y para que un cambio de paleta sea un cambio en un archivo.
"""
import altair as alt
import pandas as pd
import streamlit as st

# Paleta: un acento frío para lo neutro/institucional, verde para entrada de
# recursos y terracota para salida. Los tres bloques comerciales y los tres
# escenarios de captura reusan estos mismos colores en todas las vistas, para
# que el lector no tenga que reaprender el código de color en cada gráfico.
AZUL = "#1F6F8B"
AZUL_CLARO = "#8FC1D4"
VERDE = "#2E8B57"
TERRACOTA = "#C1554A"
AMBAR = "#D9A441"
GRIS = "#6B7280"
GRIS_CLARO = "#D1D5DB"

COLOR_BLOQUE = {
    "crecimiento": VERDE,
    "sin_senal": GRIS,
    "riesgo_retiro": TERRACOTA,
    "sin_monto_estimable": AZUL_CLARO,
}

CSS = f"""
<style>
  /* Tarjetas de KPI: el borde de acento las separa del texto corrido sin
     necesidad de recuadros pesados. */
  div[data-testid="stMetric"] {{
      background: rgba(31, 111, 139, 0.05);
      border-left: 4px solid {AZUL};
      border-radius: 4px;
      padding: 14px 16px;
  }}
  div[data-testid="stMetricLabel"] p {{
      font-size: 0.80rem;
      font-weight: 600;
      color: {GRIS};
      text-transform: uppercase;
      letter-spacing: 0.04em;
  }}
  div[data-testid="stMetricValue"] {{
      font-size: 1.65rem;
      font-weight: 700;
  }}
  div[data-testid="stMetricDelta"] {{ font-size: 0.85rem; }}

  h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
  h2 {{
      font-weight: 650;
      margin-top: 1.6rem;
      padding-bottom: 0.3rem;
      border-bottom: 2px solid {GRIS_CLARO};
  }}
  h3 {{ font-weight: 600; font-size: 1.05rem; color: {GRIS}; }}

  /* Bloques de nota: contexto que el lector necesita para no malinterpretar
     una cifra. Se distinguen por color segun sean explicativos o de cautela. */
  .nota {{
      border-left: 4px solid {AZUL};
      background: rgba(31, 111, 139, 0.06);
      padding: 12px 16px;
      border-radius: 4px;
      margin: 10px 0 16px 0;
      font-size: 0.90rem;
      line-height: 1.5;
  }}
  .cautela {{
      border-left: 4px solid {AMBAR};
      background: rgba(217, 164, 65, 0.10);
      padding: 12px 16px;
      border-radius: 4px;
      margin: 10px 0 16px 0;
      font-size: 0.90rem;
      line-height: 1.5;
  }}
  .nota b, .cautela b {{ color: inherit; }}
  .pie {{ font-size: 0.82rem; color: {GRIS}; margin-top: -6px; }}
</style>
"""

BILLON = 1e12
MIL_MILLONES = 1e9
MILLON = 1e6


def cop(valor: float, decimales: int = 2) -> str:
    """Pesos en la escala que se lee sin contar ceros (convención colombiana)."""
    if valor is None or pd.isna(valor):
        return "—"
    signo = "-" if valor < 0 else ""
    v = abs(valor)
    if v >= BILLON:
        return f"{signo}${v / BILLON:,.{decimales}f} billones"
    if v >= MIL_MILLONES:
        return f"{signo}${v / MIL_MILLONES:,.{decimales}f} mil M"
    if v >= MILLON:
        return f"{signo}${v / MILLON:,.{decimales}f} M"
    return f"{signo}${v:,.0f}"


def miles(n) -> str:
    return "—" if n is None or pd.isna(n) else f"{int(n):,}"


def nota(texto: str) -> None:
    """Contexto explicativo: qué es esta cifra y cómo se lee."""
    st.markdown(f'<div class="nota">{texto}</div>', unsafe_allow_html=True)


def cautela(texto: str) -> None:
    """Advertencia: cómo NO se debe leer esta cifra."""
    st.markdown(f'<div class="cautela">{texto}</div>', unsafe_allow_html=True)


def pie(texto: str) -> None:
    st.markdown(f'<div class="pie">{texto}</div>', unsafe_allow_html=True)


def barras_tasa(datos: pd.DataFrame, campo_cat: str, titulo_cat: str,
                tasa_base: float | None = None, alto: int = 200):
    """Barras horizontales de tasa de adopción, con la tasa base de referencia.

    La línea de la tasa base es lo que convierte el gráfico en un hallazgo:
    sin ella el lector ve porcentajes sueltos y no sabe cuáles son altos.
    """
    barras = (
        alt.Chart(datos)
        .mark_bar(cornerRadiusEnd=3, color=AZUL)
        .encode(
            y=alt.Y(f"{campo_cat}:N", sort="-x", title=titulo_cat),
            x=alt.X("tasa_adopcion:Q", title="Tasa de adopción",
                    axis=alt.Axis(format=".1%")),
            tooltip=[alt.Tooltip(f"{campo_cat}:N", title=titulo_cat),
                     alt.Tooltip("tasa_adopcion:Q", format=".2%", title="Tasa"),
                     alt.Tooltip("n_clientes:Q", format=",", title="Clientes")],
        )
    )
    if tasa_base is None:
        return barras.properties(width="container", height=alto)
    regla = (
        alt.Chart(pd.DataFrame({"base": [tasa_base]}))
        .mark_rule(color=TERRACOTA, strokeDash=[6, 4], size=2)
        .encode(x="base:Q",
                tooltip=alt.Tooltip("base:Q", format=".2%", title="Tasa base"))
    )
    return (barras + regla).properties(width="container", height=alto)
