"""Tablero de resultados de la solución analítica de la App de inversiones.

    streamlit run app/tablero.py

Seis vistas en el orden en que se cuenta la historia: qué se hizo, a quién se
analizó, cómo se predice, cuánto vale, a quién se contacta y qué no sabemos.
Cada vista abre declarando la pregunta que responde.

El estilo vive en `app/estilo.py` y la carga de datos en `app/datos.py`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

import config
from app import datos as dat
from app import estilo as es

st.set_page_config(page_title="CREAN · App de inversiones",
                   page_icon="📊", layout="wide")
st.markdown(es.CSS, unsafe_allow_html=True)

try:
    resumen = dat.jsonf("eda/resumen_ejecutivo.json")
    metricas_prop = dat.jsonf("models/metricas_propension.json")
    dimensionamiento = dat.csv("powerbi/dimensionamiento.csv")
except dat.ArtefactosFaltantes as e:
    dat.aviso_faltan_artefactos(e)

TASA_BASE = metricas_prop["tasa_adopcion"]

VISTAS = {
    "Resumen": "Qué se construyó y qué respondió",
    "Caracterización": "Quiénes son los clientes y quiénes adoptan",
    "Modelos": "Cómo se predice y qué tan bien",
    "Oportunidad": "Cuánto vale y bajo qué supuesto",
    "Priorización": "A quién contactar",
    "Sesgo y supuestos": "Qué no sabemos y qué puede salir mal",
}

with st.sidebar:
    st.markdown("### CREAN · App de inversiones")
    vista = st.radio("Vista", list(VISTAS), label_visibility="collapsed")
    st.caption(VISTAS[vista])
    st.divider()
    st.caption(
        "**Los niveles no son comparables entre poblaciones.** Cada A/B/C/D es "
        "un cuartil calculado dentro de su propia población: un 'A' con "
        "historial de inversión y un 'A' sin productos no significan lo mismo."
    )


# ===========================================================================
# Resumen
# ===========================================================================
def vista_resumen():
    st.title("Potencial de adopción de la App de inversiones")
    st.markdown(
        "Solución analítica sobre 7 fuentes del banco para **identificar los "
        "clientes con mayor probabilidad de adoptar la App** y **estimar el "
        "monto que podrían invertir en 12 meses**."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes analizados", es.miles(resumen["n_clientes_total"]),
              "el 100% de la base")
    c2.metric("Capacidad de discriminación", f"{metricas_prop['modelo_a']['auc']:.3f}",
              "AUC del modelo principal")
    c3.metric("Oportunidad de captación", es.cop(resumen["entrada_bruta_12m"]),
              f"{es.miles(resumen['n_clientes_entrada'])} clientes")
    c4.metric("Prioridad comercial alta", es.miles(resumen["n_nivel_A"]),
              "clientes en nivel A")

    es.nota(
        "La <b>oportunidad de captación</b> es el flujo de entrada bruto: la "
        "suma de lo que crecerían los clientes que el modelo proyecta creciendo. "
        "No es el cambio neto del saldo invertido — esa cifra es menor porque "
        "descuenta retiros proyectados, que son un problema de negocio distinto. "
        "Ver la vista <b>Oportunidad</b>."
    )

    st.header("La base se parte en tres, y cada parte es otra estrategia")
    base = dat.base_clientes()
    con_prod = base["poblacion"] == "con_historial"
    con_inv = base["tiene_historial_inversion"] == 1
    poblaciones = pd.DataFrame([
        {"Población": "Sin productos", "Estrategia": "Adquisición",
         "Clientes": int((~con_prod).sum()),
         "Modelo": "B · similitud", "Monto": "No estimable"},
        {"Población": "Con productos, sin inversión", "Estrategia": "Activación",
         "Clientes": int((con_prod & ~con_inv).sum()),
         "Modelo": "A · probabilidad", "Monto": "No estimable"},
        {"Población": "Con inversión previa", "Estrategia": "Crecimiento",
         "Clientes": int((con_prod & con_inv).sum()),
         "Modelo": "A · probabilidad", "Monto": "Estimado"},
    ])
    izq, der = st.columns([3, 2])
    with izq:
        st.altair_chart(
            alt.Chart(poblaciones).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("Estrategia:N", sort="-x", title=None),
                x=alt.X("Clientes:Q", title="Clientes", axis=alt.Axis(format="~s")),
                color=alt.Color("Estrategia:N", legend=None,
                                scale=alt.Scale(range=[es.AZUL, es.AZUL_CLARO, es.VERDE])),
                tooltip=["Estrategia", alt.Tooltip("Clientes:Q", format=",")],
            ).properties(width="container", height=180))
    with der:
        st.dataframe(poblaciones[["Población", "Clientes", "Monto"]],
                     hide_index=True, width="stretch")
    es.nota(
        "El monto solo se estima para quien ya tiene un producto de inversión "
        "(Invesbot, Inversión Virtual, CDT o Fiducuenta): sin historial no hay "
        "sobre qué proyectar. Para el resto el monto es <b>nulo, no cero</b> — "
        "es desconocido, no es ausencia de oportunidad."
    )

    st.header("Qué responde cada vista")
    st.dataframe(
        pd.DataFrame([{"Vista": k, "Responde": v} for k, v in VISTAS.items()][1:]),
        hide_index=True, width="stretch")


# ===========================================================================
# Caracterización
# ===========================================================================
def vista_caracterizacion():
    st.title("Caracterización de la base")
    st.markdown("**¿Quiénes son los clientes y qué distingue a los que ya invierten?**")

    forma = dat.jsonf("eda/resumen_shape.json")
    tasas = dat.csv("eda/tasas_adopcion_por_segmento.csv")

    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes", es.miles(forma["n_filas"]))
    c2.metric("Variables construidas", forma["n_columnas"])
    c3.metric("Tasa de adopción base", f"{TASA_BASE:.2%}", "referencia general")

    st.header("Quién adopta")
    es.nota(
        "En todos los gráficos la <b>línea punteada</b> es la tasa base de "
        f"{TASA_BASE:.2%}. Un grupo por encima adopta más que el promedio; uno "
        "por debajo, menos. Sin esa referencia los porcentajes no dicen nada."
    )

    izq, der = st.columns(2)
    with izq:
        st.subheader("Segmento comercial")
        st.altair_chart(
            es.barras_tasa(tasas[tasas["variable"] == "desc_segmento"],
                           "categoria", "Segmento", TASA_BASE, 150))
        es.pie(
            "Preferencial adopta al 39.9%, casi 12 veces más que personal "
            "(3.4%). Es la señal más fuerte de toda la caracterización.")
    with der:
        st.subheader("Grupo de edad")
        st.altair_chart(
            es.barras_tasa(tasas[tasas["variable"] == "grupo_edad"],
                           "categoria", "Edad", TASA_BASE, 190))
        es.pie(
            "La adopción tiene forma de campana: sube hasta 36-49 (9.5%) y cae "
            "en los extremos. Los más jóvenes (3.3%) y los mayores de 65 (4.5%) "
            "son los que menos invierten.")

    st.subheader("Tipo de vivienda")
    izq2, der2 = st.columns([3, 2])
    with izq2:
        st.altair_chart(
            es.barras_tasa(
                tasas[tasas["variable"] == "desc_tipo_de_vivienda"].dropna(
                    subset=["categoria"]),
                "categoria", "Vivienda", TASA_BASE, 160))
    with der2:
        es.cautela(
            "El 69% de la base <b>no tiene</b> dato de vivienda (591,691 "
            "clientes) y ese grupo adopta al 5.6%, por debajo de la base. Pero "
            "el faltante no es aleatorio: quien no reporta vivienda tiene un "
            "patrimonio mediano de $3.95 M contra $24 M de quien sí reporta. "
            "La variable mide, en parte, <b>profundidad de la relación con el "
            "banco</b>, no solo vivienda."
        )

    st.header("El hallazgo más fuerte de la exploración")
    faltantes = dat.csv("eda/faltantes_tasa_adopcion.csv")
    fila_con = faltantes[faltantes["falta_estimador"] == 0].iloc[0]
    fila_sin = faltantes[faltantes["falta_estimador"] == 1].iloc[0]
    razon = fila_con["tasa_adopcion"] / fila_sin["tasa_adopcion"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Con estimador de ingresos", f"{fila_con['tasa_adopcion']:.2%}",
              f"{es.miles(fila_con['n_clientes'])} clientes")
    c2.metric("Sin estimador de ingresos", f"{fila_sin['tasa_adopcion']:.2%}",
              f"{es.miles(fila_sin['n_clientes'])} clientes", delta_color="inverse")
    c3.metric("Razón entre ambos", f"{razon:.0f}×", "diferencia de adopción")

    es.nota(
        "No tener estimador de ingresos es, por sí solo, el predictor negativo "
        f"más fuerte de la base: esos clientes adoptan {razon:.0f} veces menos "
        f"(χ² = {fila_con['chi2']:,.0f}, p &lt; 0.001). La lectura de negocio es "
        "que el estimador se construye a partir de patrones transaccionales, "
        "así que su ausencia señala una <b>relación transaccional delgada</b> "
        "con el banco. Por eso la ausencia se modela como bandera explícita "
        "(<code>falta_estimador</code>) en vez de imputarse."
    )

    st.header("Distribución del score de propensión")
    base = dat.base_clientes()
    muestra = base.sample(min(40_000, len(base)), random_state=config.RANDOM_STATE)
    st.altair_chart(
        alt.Chart(muestra).mark_bar(opacity=0.75).encode(
            x=alt.X("score:Q", bin=alt.Bin(maxbins=50), title="Score de propensión"),
            y=alt.Y("count():Q", title="Clientes (muestra)", stack=None),
            color=alt.Color("poblacion:N", title="Población",
                            scale=alt.Scale(range=[es.AZUL, es.AMBAR])),
            tooltip=["poblacion:N", alt.Tooltip("count():Q", format=",")],
        ).properties(width="container", height=240))
    es.pie(
        f"Muestra aleatoria de {len(muestra):,} clientes. Las dos poblaciones "
        "se escoran con modelos distintos y sus scores no son directamente "
        "comparables entre sí: se grafican juntas solo para ver la forma.")


# ===========================================================================
# Modelos
# ===========================================================================
def vista_modelos():
    st.title("Modelos analíticos")
    st.markdown("**¿Cómo se predice la adopción y qué tan bien funciona?**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Modelo A · probabilidad", f"{metricas_prop['modelo_a']['auc']:.4f}",
              f"AUC · {metricas_prop['modelo_a']['n_features']} variables")
    c2.metric("Modelo B · similitud", f"{metricas_prop['modelo_b']['auc']:.4f}",
              f"AUC · {metricas_prop['modelo_b']['n_features']} variables")
    c3.metric("Clientes entrenables", es.miles(metricas_prop["n_entrenables"]))

    es.nota(
        "<b>Dos modelos, no uno.</b> El A usa todo el comportamiento disponible "
        "y aplica a quien tiene productos. El B usa solo capacidad financiera y "
        "aplica a quien no tiene ninguno — ahí la etiqueta de adopción es 0 por "
        "construcción, así que no hay positivos contra los cuales validar. Su "
        "AUC se mide sobre los clientes que sí tienen etiqueta y luego el "
        "modelo se aplica fuera de esa población: es un número real, pero "
        "<b>validado en otra población</b>. Por eso se presenta como similitud "
        "y no como probabilidad."
    )

    st.header("Cuántos clientes conviene contactar")
    curva = dat.csv("models/curva_precision_recall.csv")
    tabla = curva.assign(
        Esfuerzo=lambda d: d["top_pct"].map(lambda p: f"Top {p:.0%}"),
        Contactados=lambda d: d["n_contactados"].map(es.miles),
        Precisión=lambda d: d["precision"].map(lambda v: f"{v:.1%}"),
        Cobertura=lambda d: d["recall"].map(lambda v: f"{v:.1%}"),
        Lift=lambda d: (d["precision"] / TASA_BASE).map(lambda v: f"{v:.1f}×"),
    )
    izq, der = st.columns([3, 2])
    with izq:
        largo = curva.melt(id_vars="top_pct", value_vars=["precision", "recall"],
                           var_name="métrica", value_name="valor")
        largo["métrica"] = largo["métrica"].map(
            {"precision": "Precisión (aciertos)", "recall": "Cobertura (alcance)"})
        st.altair_chart(
            alt.Chart(largo).mark_line(point=True, size=3).encode(
                x=alt.X("top_pct:Q", title="Porcentaje de la base contactado",
                        axis=alt.Axis(format=".0%")),
                y=alt.Y("valor:Q", title=None, axis=alt.Axis(format=".0%")),
                color=alt.Color("métrica:N", title=None,
                                scale=alt.Scale(range=[es.AZUL, es.VERDE])),
                tooltip=[alt.Tooltip("top_pct:Q", format=".0%", title="Esfuerzo"),
                         "métrica:N", alt.Tooltip("valor:Q", format=".1%")],
            ).properties(width="container", height=260))
    with der:
        st.dataframe(
            tabla[["Esfuerzo", "Contactados", "Precisión", "Cobertura", "Lift"]],
            hide_index=True, width="stretch")

    es.nota(
        "Esta es la tabla que convierte el modelo en una decisión operativa. "
        "Contactando al <b>10% mejor rankeado</b> (17,204 clientes) se alcanza "
        "al <b>51.7% de todos los adoptantes</b> con una precisión del 37.0%, "
        f"que es <b>5.2 veces</b> la tasa base de {TASA_BASE:.1%}. Duplicar el "
        "esfuerzo al 20% sube la cobertura a 77.4% pero baja la precisión a "
        "27.7%: dónde conviene parar depende del costo del contacto."
    )

    st.header("Validación estadística de las variables")
    validacion = dat.csv("eda/validacion_variables.csv")
    conteo = (validacion["decision_inclusion"].value_counts()
              .rename_axis("Decisión").reset_index(name="Variables"))

    izq2, der2 = st.columns([2, 3])
    with izq2:
        st.altair_chart(
            alt.Chart(conteo).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("Decisión:N", sort="-x", title=None),
                x=alt.X("Variables:Q", title="Variables"),
                color=alt.Color("Decisión:N", legend=None,
                                scale=alt.Scale(range=[es.AZUL_CLARO, es.VERDE,
                                                       es.AZUL, es.GRIS, es.AMBAR])),
                tooltip=["Decisión:N", "Variables:Q"],
            ).properties(width="container", height=190))
    with der2:
        es.nota(
            "Cada variable —tanto las que vienen de las fuentes como las "
            "construidas por el pipeline— pasa por cuatro filtros: <b>IV/WoE</b> "
            "(poder predictivo), <b>prueba de significancia</b> (Mann-Whitney en "
            "continuas, χ² y V de Cramér en categóricas), <b>corrección "
            "Benjamini-Hochberg</b> (evita falsos positivos al probar 64 "
            "variables a la vez) y <b>VIF</b> (multicolinealidad).<br><br>"
            "La validación <b>rechazó variables construidas por el propio "
            "pipeline</b>, no solo variables de origen. Ese es el punto de "
            "tenerla: si nunca descarta nada, no está midiendo."
        )

    solo_incluidas = st.checkbox("Ver solo las variables que entraron al modelo")
    tabla_v = (validacion[validacion["decision_inclusion"].str.startswith("incluir")]
               if solo_incluidas else validacion)
    st.dataframe(
        tabla_v[["variable", "tipo", "iv", "clase_iv", "q_bh",
                 "significativa_fdr", "vif", "decision_inclusion"]]
        .sort_values("iv", ascending=False),
        hide_index=True, width="stretch", height=340,
        column_config={
            "variable": st.column_config.TextColumn("Variable"),
            "tipo": st.column_config.TextColumn("Tipo"),
            "iv": st.column_config.NumberColumn(
                "IV", format="%.3f",
                help="Information Value: poder predictivo. Mayor a 0.3 es fuerte; "
                     "por debajo de 0.02 se descarta."),
            "clase_iv": st.column_config.TextColumn("Clase IV"),
            "q_bh": st.column_config.NumberColumn(
                "q (BH)", format="%.4f",
                help="p-valor corregido por comparaciones múltiples."),
            "significativa_fdr": st.column_config.CheckboxColumn("Significativa"),
            "vif": st.column_config.NumberColumn(
                "VIF", format="%.1f",
                help="Multicolinealidad. Mayor a 10 es alerta; infinito indica "
                     "combinación lineal exacta con otra variable."),
            "decision_inclusion": st.column_config.TextColumn("Decisión"),
        })

    st.header("Qué variables pesan en la predicción")
    importancia = dat.csv("powerbi/fact_importancia_variables.csv")
    modelo = st.radio("Modelo", sorted(importancia["modelo"].dropna().unique()),
                      horizontal=True)
    top = importancia[importancia["modelo"] == modelo].nlargest(15, "importancia")
    st.altair_chart(
        alt.Chart(top).mark_bar(cornerRadiusEnd=3, color=es.AZUL).encode(
            y=alt.Y("variable:N", sort="-x", title=None),
            x=alt.X("importancia:Q", title="Caída del AUC al permutar la variable"),
            tooltip=["variable:N", alt.Tooltip("importancia:Q", format=".4f")],
        ).properties(width="container", height=380))
    es.pie(
        "Importancia por permutación: cuánto empeora el modelo si se desordena "
        "esa variable. Mide contribución real a la predicción, no correlación.")


# ===========================================================================
# Oportunidad
# ===========================================================================
def vista_oportunidad():
    st.title("Dimensionamiento de la oportunidad")
    st.markdown("**¿Cuánto volumen puede canalizar la App en 12 meses?**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Entrada bruta · captación", es.cop(resumen["entrada_bruta_12m"]),
              f"{es.miles(resumen['n_clientes_entrada'])} clientes")
    c2.metric("Salida bruta · retención", es.cop(resumen["salida_bruta_12m"]),
              f"{es.miles(resumen['n_clientes_salida'])} clientes",
              delta_color="inverse")
    c3.metric("Cambio neto", es.cop(resumen["neto_12m"]), "entrada menos salida")

    es.nota(
        "El modelo proyecta el <b>cambio neto</b> del saldo invertido, pero la "
        "pregunta del negocio es cuánto <b>podrían invertir</b>, que es un flujo "
        "de entrada. Son cosas distintas y conviene no mezclarlas:<br>"
        "· <b>Entrada bruta</b> → dimensionar el lanzamiento. Es la cifra del brief.<br>"
        "· <b>Cambio neto</b> → planeación financiera del saldo total.<br>"
        "· <b>Salida bruta</b> → no es un error de signo. Son clientes reales "
        "que el modelo proyecta desinvirtiendo: una base de <b>retención</b>, "
        "identificable uno a uno, con dueño distinto al de captación."
    )

    st.header("Simulador de captura comercial")
    es.cautela(
        "<b>El rango no sale del error del modelo.</b> Los dos extremos "
        "estadísticos posibles son ambos inservibles: suponer los errores "
        "perfectamente correlacionados da una banda de ancho 498% de la base, "
        "con el extremo inferior negativo; suponerlos independientes la reduce "
        "a 1.1%, precisión que una proyección a 12 meses sobre ~13 meses de "
        "historia no puede tener. La correlación real no es estimable con una "
        "sola ventana temporal.<br><br>"
        "Ese callejón sin salida <b>es</b> el hallazgo: la incertidumbre que "
        "manda no es el error del modelo, es la <b>adopción</b>. Por eso el "
        "rango se construye sobre un supuesto de negocio explícito y "
        "discutible, no sobre una precisión estadística falsa."
    )

    tasa = st.slider(
        "Tasa de captura — qué porcentaje de la entrada bruta se mueve a la App",
        0, 100, int(config.TASAS_CAPTURA["base"] * 100), step=5, format="%d%%") / 100

    izq, der = st.columns([2, 3])
    with izq:
        st.metric(f"Oportunidad con captura del {tasa:.0%}",
                  es.cop(resumen["entrada_bruta_12m"] * tasa))
        es.pie("oportunidad = entrada bruta × tasa de captura")
    with der:
        escenarios = pd.DataFrame([
            {"Escenario": n.capitalize(), "Tasa": t,
             "Oportunidad": resumen["entrada_bruta_12m"] * t}
            for n, t in config.TASAS_CAPTURA.items()])
        st.altair_chart(
            alt.Chart(escenarios).mark_bar(cornerRadiusEnd=3).encode(
                x=alt.X("Escenario:N", sort=None, title=None),
                y=alt.Y("Oportunidad:Q", title="COP a 12 meses",
                        axis=alt.Axis(format="~s")),
                color=alt.Color("Escenario:N", legend=None,
                                scale=alt.Scale(range=[es.AMBAR, es.AZUL, es.VERDE])),
                tooltip=["Escenario:N", alt.Tooltip("Tasa:Q", format=".0%"),
                         alt.Tooltip("Oportunidad:Q", format=",.0f")],
            ).properties(width="container", height=200))

    st.header("De dónde vendría el dinero")
    comp = pd.DataFrame([
        {"Componente": "App · Invesbot + Inversión Virtual",
         "Monto": float(dimensionamiento["monto_app_base"].sum()),
         "Lectura": "Negocio nuevo: crecimiento en comportamiento tipo App"},
        {"Componente": "Conservadores · CDT + Fiducuenta",
         "Monto": float(dimensionamiento["monto_prod_conservadores_base"].sum()),
         "Lectura": "Traslado: recursos que ya están en el banco"},
    ])
    izq2, der2 = st.columns([2, 3])
    with izq2:
        st.altair_chart(
            alt.Chart(comp).mark_arc(innerRadius=55).encode(
                theta="Monto:Q",
                color=alt.Color("Componente:N", title=None,
                                scale=alt.Scale(range=[es.VERDE, es.AZUL_CLARO]),
                                legend=alt.Legend(orient="bottom", columns=1)),
                tooltip=["Componente:N", alt.Tooltip("Monto:Q", format=",.0f")],
            ).properties(width="container", height=250))
    with der2:
        st.dataframe(comp.assign(Monto=comp["Monto"].map(es.cop)),
                     hide_index=True, width="stretch")
        es.nota(
            "Esta separación cambia la conversación. Aproximadamente la mitad "
            "de la oportunidad no es dinero nuevo: es saldo que ya está en CDT "
            "y Fiducuenta y que podría migrar a la App. Presentarlo como "
            "crecimiento sería contarlo dos veces a nivel banco."
        )

    st.header("Detalle por nivel, bloque y segmento")
    es.cautela(
        "Los niveles <b>B y C no diferencian monto</b>: dentro de cada uno hay "
        "un único valor distinto (17.46 COP), dispersión exactamente cero. El "
        "modelo colapsa a una constante en la zona media. Siguen siendo válidos "
        "para <b>priorizar contacto</b> —van sobre el score, que sí "
        "discrimina— pero no aportan resolución para <b>dimensionar</b>. Por "
        "eso se agrupan en el bloque <code>sin_senal</code>, derivado de la "
        "dispersión medida y no de una lista fija."
    )
    st.dataframe(
        dimensionamiento, hide_index=True, width="stretch", height=320,
        column_config={
            "nivel": st.column_config.TextColumn("Nivel"),
            "bloque_comercial": st.column_config.TextColumn("Bloque"),
            "poblacion": st.column_config.TextColumn("Población"),
            "desc_segmento": st.column_config.TextColumn("Segmento"),
            "n_clientes": st.column_config.NumberColumn("Clientes", format="%d"),
            "monto_base": st.column_config.NumberColumn("Neto", format="%.0f"),
            "monto_entrada_bruta": st.column_config.NumberColumn(
                "Entrada bruta", format="%.0f"),
            "monto_salida_bruta": st.column_config.NumberColumn(
                "Salida bruta", format="%.0f"),
            "score_medio": st.column_config.NumberColumn("Score medio", format="%.4f"),
        })


# ===========================================================================
# Priorización
# ===========================================================================
def vista_priorizacion():
    st.title("Lista de contacto priorizada")
    st.markdown("**¿A quién llama el equipo comercial el lunes?**")

    base = dat.base_clientes()

    f1, f2, f3 = st.columns(3)
    poblacion = f1.multiselect("Población", sorted(base["poblacion"].unique()),
                               default=sorted(base["poblacion"].unique()))
    nivel = f2.multiselect("Nivel de prioridad",
                           sorted(base["nivel"].dropna().unique()), default=["A"])
    segmentos = sorted(base["desc_segmento"].dropna().unique())
    segmento = f3.multiselect("Segmento", segmentos, default=segmentos)
    solo_con_monto = st.checkbox(
        "Solo clientes con monto estimado (los que ya tienen algún producto de inversión)")

    sel = base[base["poblacion"].isin(poblacion)
               & base["nivel"].isin(nivel)
               & base["desc_segmento"].isin(segmento)]
    if solo_con_monto:
        sel = sel[sel["tiene_historial_inversion"] == 1]

    if sel.empty:
        st.warning("Ningún cliente cumple los filtros seleccionados.")
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes seleccionados", es.miles(len(sel)))
    c2.metric("Entrada bruta de la selección",
              es.cop(sel["monto_base_12m"].clip(lower=0).sum()))
    c3.metric("Con monto estimado", es.miles(sel["monto_base_12m"].notna().sum()))

    if (sel["poblacion"] == "sin_historial").any():
        es.cautela(
            "La selección incluye <b>clientes sin ningún producto</b>. Su score "
            "es de <b>similitud</b>, no una probabilidad validada: en esa "
            "población la etiqueta es 0 por construcción, así que no existen "
            "positivos contra los cuales medirla. Sirve para explorar "
            "adquisición en frío; no para prometer una tasa de conversión."
        )

    COLS = ["numero_id", "poblacion", "nivel", "desc_segmento", "grupo_edad",
            "score", "modelo_usado", "monto_base_12m", "valor_esperado_12m",
            "valor_referencia", "tipo_valor_referencia"]
    lista = (sel[[c for c in COLS if c in sel.columns]]
             .sort_values("valor_referencia", ascending=False))

    tope = st.number_input(
        "Cuántos exportar (los de mayor valor de referencia)",
        min_value=min(100, len(lista)), max_value=len(lista),
        value=min(5000, len(lista)), step=100)
    lista = lista.head(int(tope))

    es.nota(
        "Ordenada por <b>valor de referencia</b>: dentro de la población con "
        "historial de inversión es <code>score × monto</code>, porque ahí "
        "importa tanto la probabilidad como el tamaño; en el resto es el score "
        "solo, porque no hay monto que estimar. La columna "
        "<code>tipo_valor_referencia</code> dice cuál se usó en cada fila."
    )

    st.dataframe(
        lista.head(200), hide_index=True, width="stretch", height=380,
        column_config={
            "numero_id": st.column_config.TextColumn(
                "ID cliente",
                help="Texto a propósito: es un entero de 19 dígitos y cualquier "
                     "herramienta que lo lea como decimal le cambia los últimos "
                     "dígitos en silencio."),
            "poblacion": st.column_config.TextColumn("Población"),
            "nivel": st.column_config.TextColumn("Nivel"),
            "desc_segmento": st.column_config.TextColumn("Segmento"),
            "grupo_edad": st.column_config.TextColumn("Edad"),
            "score": st.column_config.ProgressColumn(
                "Score", format="%.3f", min_value=0.0, max_value=1.0),
            "modelo_usado": st.column_config.TextColumn("Modelo"),
            "monto_base_12m": st.column_config.NumberColumn("Monto 12m", format="%.0f"),
            "valor_esperado_12m": st.column_config.NumberColumn(
                "Valor esperado", format="%.0f"),
            "valor_referencia": st.column_config.NumberColumn(
                "Valor referencia", format="%.4f"),
            "tipo_valor_referencia": st.column_config.TextColumn("Tipo de valor"),
        })
    es.pie(f"Vista previa de 200 filas; la descarga trae {len(lista):,}.")

    st.download_button(
        "⬇  Descargar lista de contacto (CSV)",
        lista.to_csv(index=False).encode("utf-8-sig"),
        file_name="lista_contacto_crean.csv", mime="text/csv", type="primary")


# ===========================================================================
# Sesgo y supuestos
# ===========================================================================
def vista_sesgo_y_supuestos():
    st.title("Auditoría de sesgo y supuestos")
    st.markdown("**¿Qué puede salir mal y qué estamos asumiendo?**")

    sesgo = dat.csv("powerbi/fact_auditoria_sesgo.csv")

    st.header("Proxy de género")
    if "auc_proxy_genero" in sesgo.columns and not sesgo.empty:
        auc_proxy = float(sesgo["auc_proxy_genero"].iloc[0])
        c1, c2 = st.columns([1, 3])
        c1.metric("AUC del proxy", f"{auc_proxy:.4f}",
                  str(sesgo["interpretacion_proxy_genero"].iloc[0]))
        with c2:
            es.nota(
                "El género se excluyó del modelo por <b>idoneidad, no por falta "
                "de poder predictivo</b>: si resultara predictivo reflejaría una "
                "desigualdad histórica de acceso, no una señal que el modelo "
                "deba aprender. Pero excluirlo no basta — si el resto de "
                "variables lo reconstruyen, el sesgo entra por la puerta de "
                f"atrás. Con AUC {auc_proxy:.3f} el proxy es <b>moderado</b> "
                f"(banda {config.UMBRAL_AUC_PROXY_MODERADO}–"
                f"{config.UMBRAL_AUC_PROXY_SUSTANCIAL}): se documenta y se "
                "vigila. Ni se ignora ni se sobrerreacciona."
            )

    st.header("Regla del 80% por atributo protegido")
    es.nota(
        "Compara la tasa de selección en nivel A de cada grupo contra la del "
        "grupo mejor tratado. Por debajo de 0.80 hay impacto dispar y "
        "corresponde revisar antes de operar la lista."
    )
    st.dataframe(
        sesgo, hide_index=True, width="stretch",
        column_config={
            "atributo": st.column_config.TextColumn("Atributo"),
            "grupo": st.column_config.TextColumn("Grupo"),
            "n": st.column_config.NumberColumn("Clientes", format="%d"),
            "n_seleccionados": st.column_config.NumberColumn("En nivel A", format="%d"),
            "tasa_seleccion_nivel_A": st.column_config.NumberColumn(
                "Tasa selección A", format="%.3f"),
            "razon_impacto_dispar": st.column_config.NumberColumn(
                "Razón impacto", format="%.3f",
                help="Regla del 80%: por debajo de 0.80 hay alerta de impacto dispar."),
            "cumple_regla_80": st.column_config.CheckboxColumn("Cumple 80%"),
            "p_valor_vs_resto": st.column_config.NumberColumn("p-valor", format="%.2e"),
        })
    es.cautela(
        "La razón de impacto sale <b>0.00</b> en todos los grupos porque el "
        "grupo «Sin dato» de género (93 clientes) tiene tasa de selección cero "
        "y arrastra el cociente. Es un artefacto de un grupo diminuto, no "
        "evidencia de discriminación sistemática: hay que leer las tasas de "
        "selección columna por columna antes de concluir. Entre femenino "
        "(26.7%) y masculino (23.0%) la razón real es 0.86, que sí cumple."
    )

    st.header("Supuestos que hay que decir en voz alta")
    st.markdown(
        f"""
| Supuesto | Por qué importa |
|---|---|
| El monto es un **cambio neto**, no un flujo de entrada | La cifra de captación es la entrada bruta; el neto ya descontó retiros |
| El rango agregado sale de una **tasa de captura**, no del error del modelo | Es un supuesto de negocio discutible, no una precisión estadística |
| Los niveles **B y C no diferencian monto** | Sirven para priorizar contacto, no para dimensionar |
| Horizonte de **12 meses extrapolado desde ~13 meses** de historia, validado contra 3 | El escenario base se recentró por la mediana del error porque el modelo sobre-predice |
| Los clientes **sin productos se rankean por similitud** | No hay positivos contra los cuales validar una probabilidad |
| Los niveles **no son comparables entre poblaciones** | Cada A es el 25% superior de la suya |
| La adopción se define sobre **Invesbot e Inversión Virtual** | CDT y Fiducuenta son predictores, no parte de la etiqueta |
| El corte temporal es **global y único**, con ventana de {config.VENTANA_MESES_AGREGACION} meses | Con cortes por fuente cada cliente quedaría medido en un momento distinto |
"""
    )

    st.header("Registro de decisiones")
    es.nota(
        "Trazabilidad completa: qué se decidió, por qué, y con qué evidencia "
        "medida. Se escribe en cada corrida del pipeline."
    )
    try:
        st.dataframe(dat.csv("decisiones/log_decisiones.csv"),
                     hide_index=True, width="stretch", height=340)
    except dat.ArtefactosFaltantes:
        st.info("El log de decisiones se genera al ejecutar los notebooks.")


# ===========================================================================
# Despacho
# ===========================================================================
# Cada vista carga sus propios artefactos. Si falta uno -- porque alguien
# ejecuto el pipeline a medias -- el guardian lo convierte en un aviso de esa
# vista en vez de un traceback que tumba el tablero entero.
VISTA_FN = {
    "Resumen": vista_resumen,
    "Caracterización": vista_caracterizacion,
    "Modelos": vista_modelos,
    "Oportunidad": vista_oportunidad,
    "Priorización": vista_priorizacion,
    "Sesgo y supuestos": vista_sesgo_y_supuestos,
}

try:
    VISTA_FN[vista]()
except dat.ArtefactosFaltantes as e:
    dat.aviso_vista_incompleta(e, vista)
