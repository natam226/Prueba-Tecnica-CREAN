"""Cuánto volumen puede entrar en 12 meses, cómo se calculó y qué tan confiable es."""
import altair as alt
import pandas as pd
import streamlit as st

import config
from app import datos as dat
from app import estilo as es


def render():
    resumen = dat.resumen_ejecutivo()
    dimensionamiento = dat.csv("powerbi/dimensionamiento.csv")

    st.title("La oportunidad")
    st.markdown("**¿Cuánto dinero puede canalizar la App en 12 meses?**")

    es.respuesta(
        f"Los clientes que ya invierten y que el modelo proyecta creciendo "
        f"moverían <b>{es.cop(resumen['entrada_bruta_12m'])} de pesos</b> en "
        f"los próximos 12 meses. Ese es el tamaño de la mesa.<br><br>"
        f"Cuánto de eso capta efectivamente la App <b>no lo puede decir un "
        f"modelo de saldos</b>: depende de qué tan bien se lance el producto. "
        f"Por eso la cifra se presenta con una palanca comercial explícita en "
        f"vez de un número único."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Dinero que podría entrar", es.cop(resumen["entrada_bruta_12m"]),
              f"{es.miles(resumen['n_clientes_entrada'])} clientes crecerían")
    c2.metric("Dinero que podría salir", es.cop(resumen["salida_bruta_12m"]),
              f"{es.miles(resumen['n_clientes_salida'])} clientes retirarían",
              delta_color="inverse")
    c3.metric("Diferencia neta", es.cop(resumen["neto_12m"]),
              "entrada menos salida")

    es.nota(
        "<b>Son tres cifras y responden preguntas distintas.</b><br>"
        "· Para dimensionar el lanzamiento, la cifra es la <b>entrada</b>: es "
        "el dinero que la App podría captar.<br>"
        "· Para proyectar el saldo total del banco, la cifra es la "
        "<b>neta</b>.<br>"
        "· La <b>salida</b> no es un error de signo. Son clientes reales que "
        "vienen retirando: un problema de retención, con otro dueño, que "
        "aparece gratis en el mismo análisis."
    )

    # --------------------------------------------------------------- simulador
    st.header("¿Cuánto de eso se captura realmente?")
    es.respuesta(
        "Eso es una <b>decisión y una apuesta comercial</b>, no un resultado "
        "estadístico. Mueva la barra para ver el escenario que quiera "
        "defender. El supuesto queda a la vista, que es justo lo que un "
        "comité necesita para discutirlo.",
        rotulo="Cómo usarlo")

    tasa = st.slider(
        "De cada 100 pesos que podrían moverse, ¿cuántos capta la App?",
        0, 100, int(config.TASAS_CAPTURA["base"] * 100), step=5,
        format="%d%%") / 100

    izq, der = st.columns([2, 3])
    with izq:
        st.metric(f"Oportunidad si se capta el {tasa:.0%}",
                  es.cop(resumen["entrada_bruta_12m"] * tasa))
        es.pie("dinero que podría entrar × tasa de captura")
    with der:
        escenarios = pd.DataFrame([
            {"Escenario": n.capitalize(), "Tasa": t,
             "Oportunidad": resumen["entrada_bruta_12m"] * t}
            for n, t in config.TASAS_CAPTURA.items()])
        st.altair_chart(
            alt.Chart(escenarios).mark_bar(cornerRadiusEnd=3).encode(
                x=alt.X("Escenario:N", sort=None, title=None),
                y=alt.Y("Oportunidad:Q", title="Pesos a 12 meses",
                        axis=alt.Axis(format="~s")),
                color=alt.Color("Escenario:N", legend=None,
                                scale=alt.Scale(range=[es.AMBAR, es.AZUL, es.VERDE])),
                tooltip=["Escenario:N", alt.Tooltip("Tasa:Q", format=".0%"),
                         alt.Tooltip("Oportunidad:Q", format=",.0f")],
            ).properties(width="container", height=210))

    # ------------------------------------------------------- ¿es acertado?
    st.header("¿Es un cálculo acertado?")
    es.respuesta(
        "<b>Parcialmente, y conviene ser preciso sobre qué parte.</b> El "
        "ordenamiento de clientes es sólido y está validado. La estimación de "
        "monto por cliente tiene un error mediano del 4,3%, que es razonable. "
        "Lo que <b>no</b> se puede afirmar con precisión es la cifra agregada, "
        "porque depende de cuánta gente adopte — y eso todavía no ha pasado.",
        rotulo="Respuesta honesta")

    solido, asumido = st.columns(2)
    with solido:
        st.subheader("Lo que está medido")
        st.markdown(
            """
- **Quién crece y quién no.** Sale del comportamiento observado de 219.542
  clientes durante 13 meses.
- **Cuánto crece cada uno.** Validado contra 3 meses que el modelo no vio;
  error mediano del **4,3%**.
- **El sesgo del modelo.** Se detectó que sobre-predice y la cifra ya viene
  corregida por eso.
            """)
    with asumido:
        st.subheader("Lo que es supuesto")
        st.markdown(
            """
- **La tasa de captura.** Nadie sabe cuánta gente se pasará a una App que
  todavía no existe. Es la palanca del simulador.
- **Que el pasado se parezca al futuro.** Se proyectan 12 meses con 13 meses
  de historia. Es el dato disponible, pero es poco.
- **Que la App se parezca a Invesbot e Inversión Virtual**, que es de donde
  sale la definición de "adoptante".
            """)

    with es.detalle("Por qué el rango no sale del error del modelo"):
        st.markdown(
            """
Lo intuitivo sería sumar el mejor y el peor caso de cada cliente. Medido, eso
da una banda de **ancho 498% de la cifra base**, con el extremo inferior en
negativo — porque equivale a suponer que los 219.542 clientes fallan todos a la
vez en la misma dirección.

El extremo contrario —suponer que los errores de cada cliente son
independientes— da una banda de **1,1%**. Eso implicaría que una proyección a
12 meses hecha con 13 meses de historia tiene una precisión de ±1%, lo cual
nadie se cree.

La verdad está en medio y **no es calculable**: haría falta saber cuánto se
correlacionan los errores entre clientes, y con una sola ventana de tiempo eso
no se puede estimar.

**Ese callejón sin salida es en sí mismo el hallazgo**: la incertidumbre que
manda en esta cifra no es el error del modelo, es la adopción. Por eso el rango
se construye sobre una tasa de captura declarada, que sí se puede discutir y
que se volverá medible el primer mes después del lanzamiento.
            """)

    # ----------------------------------------------------------- de dónde sale
    st.header("¿De dónde saldría ese dinero?")
    comp = pd.DataFrame([
        {"Origen": "Invesbot e Inversión Virtual",
         "Monto": float(dimensionamiento["monto_app_base"].sum()),
         "Qué significa": "Negocio nuevo: más inversión digital"},
        {"Origen": "CDT y Fiducuenta",
         "Monto": float(dimensionamiento["monto_prod_conservadores_base"].sum()),
         "Qué significa": "Traslado: plata que ya está en el banco"},
    ])
    izq2, der2 = st.columns([2, 3])
    with izq2:
        st.altair_chart(
            alt.Chart(comp).mark_arc(innerRadius=55).encode(
                theta="Monto:Q",
                color=alt.Color("Origen:N", title=None,
                                scale=alt.Scale(range=[es.VERDE, es.AZUL_CLARO]),
                                legend=alt.Legend(orient="bottom", columns=1)),
                tooltip=["Origen:N", alt.Tooltip("Monto:Q", format=",.0f")],
            ).properties(width="container", height=230))
    with der2:
        st.dataframe(comp.assign(Monto=comp["Monto"].map(es.cop)),
                     hide_index=True, width="stretch")
        es.cautela(
            "<b>Aproximadamente la mitad no es dinero nuevo.</b> Viene de CDT "
            "y Fiducuenta, es decir, de saldo que el banco ya tiene. Migrarlo "
            "a la App tiene valor —mejora la experiencia y la retención— pero "
            "presentarlo como crecimiento sería contarlo dos veces a nivel "
            "institucional. Conviene decirlo antes de que alguien lo pregunte."
        )

    with es.detalle("Detalle por nivel, bloque y segmento"):
        es.cautela(
            "Los niveles <b>B y C no diferencian monto</b>: dentro de cada uno "
            "todos los clientes tienen exactamente el mismo valor estimado. El "
            "modelo distingue bien quién crece y quién decrece, pero en la zona "
            "media no tiene resolución. Sirven para priorizar el contacto, no "
            "para repartir metas de volumen."
        )
        st.dataframe(dimensionamiento, hide_index=True, width="stretch",
                     height=300)
