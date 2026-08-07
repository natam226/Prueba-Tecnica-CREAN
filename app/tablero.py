"""Interfaz de resultados de la solución analítica (§8).

Se ejecuta con:

    streamlit run app/tablero.py

Lee los artefactos ya generados por el pipeline (`outputs/`), NO recalcula
nada: si una cifra de aquí no cuadra con un notebook, el notebook manda.

Deliberadamente NO carga `fact_saldos_mensual` (9.9 M filas): la serie mensual
se agrega en el pipeline, no en la capa de presentación.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

import config

st.set_page_config(page_title="CREAN — App de inversiones", layout="wide")

MILLON = 1e6
MIL_MILLONES = 1e9


def cop(valor: float) -> str:
    """Formatea pesos en la unidad que se lee sin contar ceros."""
    if pd.isna(valor):
        return "—"
    if abs(valor) >= MIL_MILLONES:
        return f"${valor / MIL_MILLONES:,.1f} mil M"
    if abs(valor) >= MILLON:
        return f"${valor / MILLON:,.1f} M"
    return f"${valor:,.0f}"


@st.cache_data
def cargar_csv(ruta_relativa: str) -> pd.DataFrame:
    return pd.read_csv(config.OUTPUTS_DIR / ruta_relativa)


@st.cache_data
def cargar_json(ruta_relativa: str) -> dict:
    with open(config.OUTPUTS_DIR / ruta_relativa, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def cargar_base_clientes() -> pd.DataFrame:
    """Score por cliente + demografía, que es lo que consume la lista de contacto."""
    score = cargar_csv("powerbi/fact_cliente_score.csv")
    dim = cargar_csv("powerbi/dim_cliente.csv")
    cols_dim = [c for c in ["numero_id", "desc_segmento", "grupo_edad"] if c in dim.columns]
    return score.merge(dim[cols_dim], on="numero_id", how="left")


def aviso_faltan_datos(error: Exception) -> None:
    st.error(
        f"No se encontraron los artefactos del pipeline ({error}).\n\n"
        "Ejecutar primero `python scripts/run_pipeline.py`, los notebooks 02 a 07 "
        "y `python scripts/export_powerbi.py`."
    )
    st.stop()


try:
    dimensionamiento = cargar_csv("powerbi/dimensionamiento.csv")
    resumen = cargar_json("eda/resumen_ejecutivo.json")
    metricas_prop = cargar_json("models/metricas_propension.json")
except (FileNotFoundError, OSError) as e:  # noqa: BLE001
    aviso_faltan_datos(e)


VISTAS = [
    "1 · Dimensionamiento",
    "2 · Lista de contacto",
    "3 · Sustento del modelo",
    "4 · Sesgo y supuestos",
]
vista = st.sidebar.radio("Vista", VISTAS)
st.sidebar.caption(
    "Los niveles A/B/C/D son cuartiles calculados DENTRO de cada población: "
    "un 'A' con historial y un 'A' sin historial no son comparables entre sí."
)


# ---------------------------------------------------------------------------
# 1 · Dimensionamiento
# ---------------------------------------------------------------------------
if vista == VISTAS[0]:
    st.title("Dimensionamiento de la oportunidad")
    st.caption(
        "El modelo de monto proyecta el CAMBIO NETO del saldo invertido. La "
        "pregunta del negocio —cuánto podrían invertir— la responde la entrada "
        "bruta; el neto ya le restó los retiros proyectados."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Entrada bruta — captación", cop(resumen["entrada_bruta_12m"]),
              f"{resumen['n_clientes_entrada']:,} clientes")
    c2.metric("Salida bruta — retención", cop(resumen["salida_bruta_12m"]),
              f"{resumen['n_clientes_salida']:,} clientes", delta_color="inverse")
    c3.metric("Neto", cop(resumen["neto_12m"]),
              f"{resumen['n_clientes_con_monto']:,} clientes con monto")

    st.divider()
    st.subheader("Simulador de captura")
    st.caption(
        "La incertidumbre que manda NO es el error del modelo, es la adopción. "
        "Los dos extremos estadísticos posibles acotan el problema y ambos son "
        "absurdos: suponer los errores perfectamente correlacionados da una "
        "banda de ancho 498% de la base (con el extremo inferior en negativo), "
        "y suponerlos independientes da 1.1%. La correlación real no es "
        "estimable con una sola ventana temporal, así que el rango se construye "
        "sobre una palanca de negocio explícita en vez de sobre una precisión "
        "que los datos no soportan."
    )

    tasa = st.slider("Tasa de captura: % de la entrada bruta que efectivamente "
                     "se mueve a la App", 0, 100,
                     int(config.TASAS_CAPTURA["base"] * 100), step=5) / 100
    st.metric(f"Oportunidad a 12 meses con captura del {tasa:.0%}",
              cop(resumen["entrada_bruta_12m"] * tasa))

    referencia = pd.DataFrame([
        {"escenario": nombre, "tasa de captura": f"{t:.0%}",
         "oportunidad 12m": cop(resumen["entrada_bruta_12m"] * t)}
        for nombre, t in config.TASAS_CAPTURA.items()
    ])
    st.dataframe(referencia, hide_index=True, width="stretch")

    st.divider()
    st.subheader("Las tres poblaciones son tres estrategias distintas")
    base = cargar_base_clientes()
    con_hist_prod = base["poblacion"] == "con_historial"
    con_inv = base["tiene_historial_inversion"] == 1
    poblaciones = pd.DataFrame([
        {"población": "Sin productos", "estrategia": "Adquisición",
         "clientes": int((~con_hist_prod).sum()),
         "modelo": "B — similitud (lookalike)", "monto": "no estimable"},
        {"población": "Con productos, sin inversión", "estrategia": "Activación",
         "clientes": int((con_hist_prod & ~con_inv).sum()),
         "modelo": "A — probabilidad", "monto": "no estimable"},
        {"población": "Con inversión", "estrategia": "Crecimiento",
         "clientes": int((con_hist_prod & con_inv).sum()),
         "modelo": "A — probabilidad", "monto": "estimado"},
    ])
    st.dataframe(poblaciones, hide_index=True, width="stretch")

    st.subheader("Composición del monto base")
    st.caption(
        "Separar los dos componentes cambia la lectura: lo que viene de CDT y "
        "Fiducuenta no es negocio nuevo, es traslado de recursos que ya están "
        "en el banco."
    )
    comp = pd.DataFrame([
        {"componente": "App (Invesbot + Inversión Virtual)",
         "monto base": dimensionamiento["monto_app_base"].sum(),
         "lectura": "crecimiento en comportamiento tipo App"},
        {"componente": "Conservadores (CDT + Fiducuenta)",
         "monto base": dimensionamiento["monto_prod_conservadores_base"].sum(),
         "lectura": "migración potencial desde productos existentes"},
    ])
    comp["monto base"] = comp["monto base"].map(cop)
    st.dataframe(comp, hide_index=True, width="stretch")

    with st.expander("Detalle por nivel, bloque, población y segmento"):
        st.dataframe(dimensionamiento, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# 2 · Lista de contacto
# ---------------------------------------------------------------------------
elif vista == VISTAS[1]:
    st.title("Lista de contacto priorizada")
    st.caption(
        "El entregable accionable: filtrar, revisar y descargar la base a "
        "contactar. Ordenada por `valor_referencia`, que dentro de la población "
        "con historial es score × monto y en el resto es el score."
    )

    base = cargar_base_clientes()

    f1, f2, f3, f4 = st.columns(4)
    poblacion = f1.multiselect("Población", sorted(base["poblacion"].unique()),
                               default=sorted(base["poblacion"].unique()))
    nivel = f2.multiselect("Nivel", sorted(base["nivel"].dropna().unique()),
                           default=["A"])
    segmentos = sorted(base["desc_segmento"].dropna().unique())
    segmento = f3.multiselect("Segmento", segmentos, default=segmentos)
    solo_con_monto = f4.checkbox("Solo clientes con monto estimado", value=False)

    sel = base[base["poblacion"].isin(poblacion)
               & base["nivel"].isin(nivel)
               & base["desc_segmento"].isin(segmento)]
    if solo_con_monto:
        sel = sel[sel["tiene_historial_inversion"] == 1]

    if (sel["poblacion"] == "sin_historial").any():
        st.warning(
            "La selección incluye clientes SIN productos. Su score es de "
            "SIMILITUD, no una probabilidad validada: en esa población la "
            "etiqueta es 0 por construcción, así que no existen positivos "
            "contra los cuales medirla. Úsese para explorar, no para prometer "
            "una tasa de conversión."
        )

    m1, m2, m3 = st.columns(3)
    m1.metric("Clientes seleccionados", f"{len(sel):,}")
    m2.metric("Entrada bruta de la selección",
              cop(sel["monto_base_12m"].clip(lower=0).sum()))
    m3.metric("Con monto estimado", f"{int(sel['monto_base_12m'].notna().sum()):,}")

    COLS_LISTA = ["numero_id", "poblacion", "nivel", "desc_segmento", "grupo_edad",
                  "score", "modelo_usado", "monto_base_12m", "valor_esperado_12m",
                  "valor_referencia", "tipo_valor_referencia"]
    cols = [c for c in COLS_LISTA if c in sel.columns]
    lista = sel[cols].sort_values("valor_referencia", ascending=False)

    tope = st.number_input("Clientes a exportar (los de mayor valor de referencia)",
                           min_value=100, max_value=len(lista) if len(lista) else 100,
                           value=min(5000, len(lista)) if len(lista) else 100,
                           step=100)
    lista = lista.head(int(tope))

    st.dataframe(lista.head(200), hide_index=True, width="stretch")
    st.caption(f"Vista previa de 200 filas; la descarga trae {len(lista):,}.")
    st.download_button(
        "Descargar lista de contacto (CSV)",
        lista.to_csv(index=False).encode("utf-8"),
        file_name="lista_contacto_crean.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# 3 · Sustento del modelo
# ---------------------------------------------------------------------------
elif vista == VISTAS[2]:
    st.title("Sustento del modelo")

    c1, c2, c3 = st.columns(3)
    c1.metric("AUC Modelo A — probabilidad", f"{metricas_prop['modelo_a']['auc']:.4f}",
              f"{metricas_prop['modelo_a']['n_features']} variables")
    c2.metric("AUC Modelo B — similitud", f"{metricas_prop['modelo_b']['auc']:.4f}",
              f"{metricas_prop['modelo_b']['n_features']} variables")
    c3.metric("Tasa de adopción observada", f"{metricas_prop['tasa_adopcion']:.2%}")
    st.caption(
        "El AUC del Modelo B se mide sobre los clientes que SÍ tienen etiqueta y "
        "después el modelo se aplica a los que no tienen productos. Es un número "
        "real, pero validado fuera de la población donde se usa: por eso se "
        "presenta como similitud y no como probabilidad."
    )

    st.divider()
    st.subheader("Validación estadística de variables")
    st.caption(
        "Cada variable —tanto las propias de las fuentes como las construidas— "
        "pasa por IV/WoE, prueba de significancia (Mann-Whitney U en continuas, "
        "chi² y V de Cramér en categóricas), corrección Benjamini-Hochberg por "
        "comparaciones múltiples, y VIF de multicolinealidad."
    )
    validacion = cargar_csv("eda/validacion_variables.csv")

    resumen_dec = (validacion["decision_inclusion"].value_counts()
                   .rename_axis("decisión").reset_index(name="variables"))
    st.dataframe(resumen_dec, hide_index=True, width="stretch")
    st.caption(
        "La validación rechazó variables construidas por el propio pipeline, no "
        "solo variables de origen: es el punto de tenerla."
    )

    solo_incluidas = st.checkbox("Ver solo las variables incluidas", value=False)
    tabla = validacion
    if solo_incluidas:
        tabla = tabla[tabla["decision_inclusion"].str.startswith("incluir")]
    st.dataframe(
        tabla[["variable", "tipo", "iv", "clase_iv", "q_bh", "significativa_fdr",
               "vif", "decision_inclusion"]].sort_values("iv", ascending=False),
        hide_index=True, width="stretch", height=420,
    )

    st.divider()
    st.subheader("Importancia por permutación")
    importancia = cargar_csv("powerbi/fact_importancia_variables.csv")
    modelo = st.radio("Modelo", sorted(importancia["modelo"].dropna().unique()),
                      horizontal=True)
    imp = (importancia[importancia["modelo"] == modelo]
           .nlargest(20, "importancia")
           .set_index("variable")["importancia"])
    st.bar_chart(imp)


# ---------------------------------------------------------------------------
# 4 · Sesgo y supuestos
# ---------------------------------------------------------------------------
else:
    st.title("Auditoría de sesgo y supuestos")

    st.subheader("Regla del 80% por atributo protegido")
    sesgo = cargar_csv("powerbi/fact_auditoria_sesgo.csv")
    st.dataframe(sesgo, hide_index=True, width="stretch")

    if "auc_proxy_genero" in sesgo.columns and not sesgo.empty:
        auc_proxy = float(sesgo["auc_proxy_genero"].iloc[0])
        st.metric("AUC del proxy de género", f"{auc_proxy:.4f}",
                  str(sesgo["interpretacion_proxy_genero"].iloc[0]))
        st.caption(
            f"El género se excluyó del modelo, pero eso no basta: si el resto de "
            f"variables lo reconstruyen, el sesgo entra por la puerta de atrás. "
            f"Con AUC {auc_proxy:.3f} el proxy es moderado (banda "
            f"{config.UMBRAL_AUC_PROXY_MODERADO}–"
            f"{config.UMBRAL_AUC_PROXY_SUSTANCIAL}): se documenta y se vigila, no "
            f"se ignora ni se sobrerreacciona."
        )

    st.divider()
    st.subheader("Supuestos que hay que decir en voz alta")
    st.markdown(
        "- **El monto es un cambio neto, no un flujo de entrada.** La cifra de "
        "captación es la entrada bruta; el neto descuenta retiros proyectados.\n"
        "- **El rango agregado no sale del error del modelo,** sale de una tasa "
        "de captura explícita. Ver el simulador en la vista 1.\n"
        "- **Los niveles B y C no diferencian monto:** tienen un único valor "
        "distinto cada uno. Sirven para priorizar contacto, no para dimensionar.\n"
        "- **Horizonte de 12 meses extrapolado desde ~13 meses de historia,** "
        "validado contra 3 meses. El escenario base está recentrado por la "
        "mediana del error de backtest porque el modelo sobre-predice.\n"
        "- **Los clientes sin productos se rankean por similitud,** no por "
        "probabilidad validada.\n"
        "- **Los niveles no son comparables entre poblaciones:** cada 'A' es el "
        "25% superior de la suya."
    )

    st.divider()
    st.subheader("Registro de decisiones")
    st.caption("Trazabilidad de los supuestos: qué se decidió, por qué, y con qué evidencia.")
    try:
        st.dataframe(cargar_csv("decisiones/log_decisiones.csv"),
                     hide_index=True, width="stretch", height=380)
    except (FileNotFoundError, OSError):
        st.info("El log de decisiones se genera al ejecutar los notebooks.")
