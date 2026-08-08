"""Qué se propone, cómo funciona y qué tan bien funciona."""
import altair as alt
import streamlit as st

from app import datos as dat
from app import estilo as es


def render():
    metricas = dat.metricas_propension()
    tasa_base = dat.tasa_base()

    st.title("La solución")
    st.markdown("**¿Qué se construyó y qué tan bien funciona?**")

    es.respuesta(
        "Un sistema que le pone a cada uno de los 860.223 clientes "
        "<b>dos números</b>: qué tan probable es que adopte la App, y cuánto "
        "dinero movería si lo hace. Con esos dos se arma la lista de "
        "priorización comercial.<br><br>"
        "Hicieron falta <b>dos modelos distintos</b> porque no de todos los "
        "clientes se sabe lo mismo, y un tercero para el monto."
    )

    # ------------------------------------------------------------ los modelos
    st.header("Por qué dos modelos y no uno")

    izq, der = st.columns(2)
    with izq:
        st.subheader("Modelo A · probabilidad")
        st.metric("Aciertos", f"{metricas['modelo_a']['auc']:.3f}",
                  f"{metricas['modelo_a']['n_features']} variables")
        st.markdown(
            "Se aplica a los **529.470 clientes con productos**. Usa todo lo "
            "que se sabe de ellos: saldos, tendencias, antigüedad, capacidad "
            "financiera. Entrega una **probabilidad real**."
        )
    with der:
        st.subheader("Modelo B · parecido")
        st.metric("Aciertos", f"{metricas['modelo_b']['auc']:.3f}",
                  f"{metricas['modelo_b']['n_features']} variables")
        st.markdown(
            "Se aplica a los **330.753 clientes sin ningún producto**. Solo "
            "puede usar capacidad financiera. Entrega un **puntaje de "
            "parecido**, no una probabilidad."
        )

    es.cautela(
        "<b>La diferencia importa al vender.</b> Un cliente sin productos no "
        "puede tener saldo en Invesbot, así que en esa población "
        "<i>nadie</i> figura como adoptante — no hay contra qué comparar. Su "
        "puntaje responde «¿cuánto se parece este cliente a los que sí "
        "invierten?», que es útil para explorar adquisición en frío, pero "
        "<b>no se puede prometer como tasa de conversión</b>."
    )

    # --------------------------------------------------------- qué significa AUC
    st.header("¿Qué tan bien funciona? Traducido")
    es.respuesta(
        "Si tomamos al azar un cliente que sí invierte y otro que no, el "
        "modelo le da mayor puntaje al correcto <b>89 de cada 100 veces</b>. "
        "Para un problema comercial eso es un desempeño alto: el azar acertaría "
        "50 de cada 100.",
        rotulo="Qué significa 0,894")

    with es.detalle("Qué es el AUC y por qué se usa esa métrica"):
        st.markdown(
            f"""
El **AUC** (área bajo la curva ROC) mide exactamente lo que dice el párrafo de
arriba: la probabilidad de que el modelo ordene correctamente un par formado
por un adoptante y un no adoptante. 0,5 es azar puro y 1,0 es perfecto.

Se usa esta métrica y no la "precisión" porque el problema está **muy
desbalanceado**: solo {tasa_base:.1%} de los clientes invierte. Un modelo que
dijera "nadie invierte" acertaría el {1 - tasa_base:.1%} de las veces y sería
completamente inútil. El AUC no se deja engañar por eso.

**El AUC del Modelo B (0,838) tiene una salvedad**: se mide sobre los clientes
que sí tienen etiqueta y luego el modelo se aplica a los que no tienen
productos. Es un número real, pero **validado en una población distinta de
aquella donde se usa**.
            """)

    # ------------------------------------------------------- cómo se predice
    st.header("¿Cómo se decide que alguien va a adoptar?")
    es.respuesta(
        "El modelo no usa una regla fija tipo «si gana más de X, entonces "
        "sí». Aprende de los <b>61.636 clientes que ya tienen productos de "
        "inversión digital</b> qué combinaciones de características los "
        "distinguen, y busca esas combinaciones en el resto de la base.",
        rotulo="En corto")

    with es.detalle("El algoritmo y por qué se eligió"):
        st.markdown(
            """
Se usa **Gradient Boosting sobre árboles de decisión**
(`HistGradientBoostingClassifier`). Cuatro razones concretas:

1. **Maneja datos faltantes sin inventarlos.** Como vimos, la ausencia de dato
   es informativa en esta base; imputar habría destruido señal.
2. **Captura combinaciones**, no solo efectos sueltos. "Ingreso alto *y*
   antigüedad corta" puede significar algo distinto que cada cosa por separado.
3. **Tolera variables correlacionadas entre sí**, lo que permite conservar
   saldos y promedios del mismo producto sin tener que elegir.
4. **Escala bien** a 860 mil clientes.

La validación es **80/20 estratificada**: el modelo se entrena con el 80% y se
mide sobre el 20% que nunca vio.
            """)

    # ------------------------------------------------- validación de variables
    st.header("¿Por qué esas variables y no otras?")
    es.respuesta(
        "Ninguna variable entró por intuición. Las <b>64 candidatas</b> "
        "pasaron por cuatro filtros —¿separa a los grupos?, ¿la diferencia es "
        "real o casualidad?, ¿sobrevive a probar 64 cosas a la vez?, ¿aporta "
        "algo que otra no aporte ya?— y cada resultado quedó registrado.<br><br>"
        "Entraron <b>54</b>. Se descartaron <b>9</b> y una se excluyó por "
        "criterio ético, no por desempeño.",
        rotulo="Respuesta")

    validacion = dat.csv("eda/validacion_variables.csv")
    conteo = (validacion["decision_inclusion"].value_counts()
              .rename_axis("Decisión").reset_index(name="Variables"))
    LEGIBLE = {
        "incluir": "Entra al modelo",
        "incluir_con_alerta_multicolinealidad": "Entra, con aviso de redundancia",
        "descartar_iv_insuficiente": "Se descarta: no separa lo suficiente",
        "descartar": "Se descarta: redundante",
        "excluida_por_idoneidad_no_por_poder_predictivo": "Se excluye por criterio ético",
    }
    conteo["Decisión"] = conteo["Decisión"].map(lambda d: LEGIBLE.get(d, d))

    izq2, der2 = st.columns([3, 2])
    with izq2:
        st.altair_chart(
            alt.Chart(conteo).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("Decisión:N", sort="-x", title=None),
                x=alt.X("Variables:Q", title="Cuántas variables"),
                color=alt.condition(
                    alt.datum.Decisión == "Entra al modelo",
                    alt.value(es.VERDE), alt.value(es.AZUL_CLARO)),
                tooltip=["Decisión:N", "Variables:Q"],
            ).properties(width="container", height=200))
    with der2:
        es.respuesta(
            "El filtro <b>rechazó variables que nosotros mismos "
            "construimos</b>, no solo las que venían de las fuentes. Cuatro de "
            "las nueve descartadas fueron invenciones de este proyecto que no "
            "aportaron nada.<br><br>Un filtro que nunca descarta no está "
            "midiendo.",
            rotulo="La señal de que sirve")

    with es.detalle("Los cuatro filtros, uno por uno"):
        st.markdown(
            """
| Filtro | Qué pregunta | Umbral |
|---|---|---|
| **Information Value** | ¿Separa a quien invierte de quien no? | IV ≥ 0,02 |
| **Mann-Whitney / chi²** | ¿La diferencia es real o azar? | p < 0,05 |
| **Benjamini-Hochberg** | Al probar 64 variables, ¿sobrevive? | q corregido |
| **VIF** | ¿Aporta algo que otra no aporte ya? | VIF < 10 |

El tercero merece explicación: probar 64 variables con 5% de tolerancia produce
**unas 3 variables que parecen buenas por pura casualidad**. La corrección de
Benjamini-Hochberg controla eso. Se prefiere a Bonferroni porque este último es
tan estricto con 64 pruebas que descartaría variables genuinamente útiles.
            """)
        st.dataframe(
            validacion[["variable", "iv", "clase_iv", "significativa_fdr",
                        "vif", "decision_inclusion"]]
            .sort_values("iv", ascending=False),
            hide_index=True, width="stretch", height=300,
            column_config={
                "variable": st.column_config.TextColumn("Variable"),
                "iv": st.column_config.NumberColumn("IV", format="%.3f"),
                "clase_iv": st.column_config.TextColumn("Fuerza"),
                "significativa_fdr": st.column_config.CheckboxColumn("Significativa"),
                "vif": st.column_config.NumberColumn("VIF", format="%.1f"),
                "decision_inclusion": st.column_config.TextColumn("Decisión"),
            })

    # ------------------------------------------------------------ importancia
    st.header("¿Qué variables pesan más?")
    importancia = dat.csv("powerbi/fact_importancia_variables.csv")
    modelo = st.radio("Modelo", sorted(importancia["modelo"].dropna().unique()),
                      horizontal=True)
    top = importancia[importancia["modelo"] == modelo].nlargest(12, "importancia")

    izq3, der3 = st.columns([3, 2])
    with izq3:
        st.altair_chart(
            alt.Chart(top).mark_bar(cornerRadiusEnd=3, color=es.AZUL).encode(
                y=alt.Y("variable:N", sort="-x", title=None),
                x=alt.X("importancia:Q", title="Cuánto empeora el modelo sin ella"),
                tooltip=["variable:N", alt.Tooltip("importancia:Q", format=".4f")],
            ).properties(width="container", height=320))
    with der3:
        es.respuesta(
            "Manda la <b>relación con el banco</b>, no la demografía: cuántos "
            "productos tiene, cuánto saldo líquido maneja, hace cuánto es "
            "cliente y qué tan reciente es su actividad.<br><br>"
            "La edad y el tipo de vivienda aparecen mucho más abajo. El género "
            "no aparece: no está en el modelo.",
            rotulo="Cómo leerlo")
        es.pie(
            "Se mide desordenando cada variable y viendo cuánto empeora el "
            "modelo. Mide contribución real, no correlación.")
