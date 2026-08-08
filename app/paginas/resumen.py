"""Qué se hizo y para qué."""
import altair as alt
import pandas as pd
import streamlit as st

from app import datos as dat
from app import estilo as es


def render():
    resumen = dat.resumen_ejecutivo()
    metricas = dat.metricas_propension()

    st.title("Potencial de adopción de la App de inversiones")

    es.respuesta(
        "CREAN va a lanzar una App de inversiones y necesita saber "
        "<b>a quién ofrecérsela</b> y <b>cuánto dinero podría entrar</b>. "
        "Integramos las 7 fuentes del banco, ordenamos a los "
        "<b>860.223 clientes</b> por probabilidad de adoptar, y estimamos el "
        "monto que moverían los que ya invierten. El resultado es una lista de "
        "contacto priorizada y una cifra de oportunidad con su supuesto a la "
        "vista."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes analizados", es.miles(resumen["n_clientes_total"]),
              "el 100% de la base")
    c2.metric("Oportunidad de captación", es.cop(resumen["entrada_bruta_12m"]),
              f"{es.miles(resumen['n_clientes_entrada'])} clientes crecerían")
    c3.metric("Prioridad alta", es.miles(resumen["n_nivel_A"]),
              "clientes en nivel A")
    c4.metric("Aciertos del modelo", f"{metricas['modelo_a']['auc']:.3f}",
              "capacidad de discriminación")

    st.header("El problema de fondo: la App todavía no existe")
    es.nota(
        "Nadie ha adoptado nunca esta App, así que no hay historial de "
        "adopción que aprender. Lo resolvimos buscando en la base los "
        "productos que más se parecen a lo que la App va a ser —<b>Invesbot e "
        "Inversión Virtual</b>, los dos productos de inversión digitales— y "
        "usando su tenencia como sustituto. Todo el trabajo está construido "
        "para que ese sustituto se reemplace por datos reales el día del "
        "lanzamiento."
    )

    with es.detalle("Qué tan buena es esa aproximación — y su punto débil"):
        st.markdown(
            """
De los **61.636 clientes** marcados como adoptantes:

| Producto | Clientes | Peso en la etiqueta |
|---|---|---|
| Solo Inversión Virtual | 56.592 | **91,8%** |
| Solo Invesbot | 3.020 | 4,9% |
| Ambos | 2.024 | 3,3% |

**Invesbot pesa apenas el 8%**, y es el producto conceptualmente más cercano a
la App. Usar solo Invesbot habría dado una tasa base de 0,59% — demasiado raro
para modelar con estabilidad. La unión fue una decisión pragmática y conviene
declararla.

Se probó una definición alternativa que exige actividad en los últimos 90 días:
el AUC pasa de 0,8942 a 0,8909 y la correlación de rangos entre ambos
ordenamientos es 0,99. **La elección de etiqueta es robusta**: solo el 9,7% de
los clientes cambia de nivel y casi todos se mueven un solo escalón.
            """)

    st.header("La base se parte en tres, y cada parte es otra estrategia")
    es.respuesta(
        "No se le puede hablar igual a quien ya invierte, a quien es cliente "
        "pero nunca ha invertido, y a quien no tiene ningún producto. Son tres "
        "conversaciones comerciales distintas, y <b>solo en una de las tres se "
        "puede estimar cuánto dinero moverá</b>.",
        rotulo="Por qué importa")

    base = dat.base_clientes()
    con_prod = base["poblacion"] == "con_historial"
    con_inv = base["tiene_historial_inversion"] == 1
    poblaciones = pd.DataFrame([
        {"Estrategia": "Adquisición", "Quiénes son": "Sin ningún producto",
         "Clientes": int((~con_prod).sum()),
         "Qué se puede decir": "Se parecen a quienes invierten",
         "¿Monto?": "No estimable"},
        {"Estrategia": "Activación", "Quiénes son": "Clientes sin inversión",
         "Clientes": int((con_prod & ~con_inv).sum()),
         "Qué se puede decir": "Probabilidad de adoptar",
         "¿Monto?": "No estimable"},
        {"Estrategia": "Crecimiento", "Quiénes son": "Ya invierten",
         "Clientes": int((con_prod & con_inv).sum()),
         "Qué se puede decir": "Probabilidad y monto",
         "¿Monto?": "Estimado"},
    ])

    izq, der = st.columns([2, 3])
    with izq:
        st.altair_chart(
            alt.Chart(poblaciones).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("Estrategia:N", sort="-x", title=None),
                x=alt.X("Clientes:Q", title="Clientes",
                        axis=alt.Axis(format="~s")),
                color=alt.Color("Estrategia:N", legend=None,
                                scale=alt.Scale(range=[es.AZUL, es.AZUL_CLARO,
                                                       es.VERDE])),
                tooltip=["Estrategia:N", alt.Tooltip("Clientes:Q", format=",")],
            ).properties(width="container", height=170))
    with der:
        st.dataframe(poblaciones, hide_index=True, width="stretch")

    es.nota(
        "Para las dos primeras poblaciones el monto queda <b>vacío, no en "
        "cero</b>. Cero diría «se calculó y da cero»; vacío dice «no se puede "
        "calcular». Poner cero haría que 640.681 clientes aportaran cero a la "
        "cifra de oportunidad como si se hubiera medido."
    )

    st.header("Qué encontrará en cada sección")
    st.dataframe(pd.DataFrame([
        {"Sección": "Los clientes", "Responde": "Qué distingue a quien invierte de quien no"},
        {"Sección": "La solución", "Responde": "Qué modelos se usan y qué tan bien funcionan"},
        {"Sección": "La oportunidad", "Responde": "Cuánto dinero puede entrar en 12 meses"},
        {"Sección": "A quién contactar", "Responde": "Cuántas llamadas hacer y a quiénes"},
        {"Sección": "Supuestos y sesgos", "Responde": "Qué asumimos y qué puede salir mal"},
        {"Sección": "Cómo opera", "Responde": "Cómo vive esto dentro de CREAN"},
    ]), hide_index=True, width="stretch")
