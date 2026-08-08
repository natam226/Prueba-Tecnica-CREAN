"""Qué distingue a quien invierte de quien no, y qué hace potencial a un cliente."""
import altair as alt
import streamlit as st

from app import datos as dat
from app import estilo as es


def render():
    tasa_base = dat.tasa_base()
    tasas = dat.csv("eda/tasas_adopcion_por_segmento.csv")
    forma = dat.jsonf("eda/resumen_shape.json")

    st.title("Los clientes")
    st.markdown("**¿Qué distingue a quien ya invierte de quien no?**")

    es.respuesta(
        "Tres cosas separan a un inversionista de quien no lo es, y en este "
        "orden: <b>el segmento comercial</b> (un cliente preferencial invierte "
        "12 veces más que uno personal), <b>qué tanto se mueve su plata con el "
        "banco</b>, y <b>la edad</b> (el pico está entre los 36 y 49 años). "
        "El género prácticamente no discrimina y además se excluyó del modelo "
        "a propósito."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes en la base", es.miles(forma["n_filas"]))
    c2.metric("De cada 100 clientes, invierten", f"{tasa_base * 100:.0f}",
              "esta es la referencia")
    c3.metric("Variables analizadas", forma["n_columnas"])

    es.nota(
        f"En todos los gráficos la <b>línea punteada</b> marca el promedio "
        f"general: <b>{tasa_base:.1%}</b> de los clientes invierte hoy. Estar "
        "por encima significa invertir más que el promedio; por debajo, menos. "
        "Sin esa referencia un porcentaje suelto no dice nada."
    )

    # ---------------------------------------------------------------- segmento
    st.header("1. El segmento comercial es el factor más fuerte")
    izq, der = st.columns([3, 2])
    with izq:
        st.altair_chart(
            es.barras_tasa(tasas[tasas["variable"] == "desc_segmento"],
                           "categoria", "Segmento", tasa_base, 150))
    with der:
        es.respuesta(
            "Casi <b>4 de cada 10</b> clientes preferenciales ya invierten, "
            "contra <b>3 de cada 100</b> del segmento personal. Es una "
            "diferencia de casi 12 veces: ninguna otra variable se le acerca.",
            rotulo="Qué dice")

    # -------------------------------------------------------------- transaccional
    st.header("2. Qué tanto se mueve la plata del cliente con el banco")
    faltantes = dat.csv("eda/faltantes_tasa_adopcion.csv")
    n_sin = int(faltantes[faltantes["falta_estimador"] == 1]["n_clientes"].iloc[0])

    es.respuesta(
        f"Hay <b>{n_sin:,} clientes</b> a los que el banco no le puede estimar "
        "el ingreso. Ese estimador se construye mirando cómo entra y sale la "
        "plata, así que no tenerlo significa que <b>el cliente casi no "
        "transacciona con nosotros</b> — tiene el producto, pero su vida "
        "financiera ocurre en otra parte.<br><br>"
        "Entre clientes comparables, los que no tienen ese dato invierten "
        "<b>5,6 veces menos</b>. No es que falte un campo en una tabla: es la "
        "señal de una relación delgada.".replace(",", "."),
        rotulo="Traducido")

    c1, c2, c3 = st.columns(3)
    c1.metric("Con relación transaccional", "12,1%", "de ellos invierten")
    c2.metric("Con relación delgada", "2,2%", "de ellos invierten",
              delta_color="inverse")
    c3.metric("Diferencia", "5,6×", "entre clientes comparables")

    with es.detalle("Por qué 5,6 veces y no 19 — la comparación correcta"):
        st.markdown(
            """
La comparación directa sobre toda la base da **8,20% contra 0,44%**, es decir
19 veces. Pero esa cifra está **confundida**: el 80% de los clientes sin
estimador tampoco tiene ningún producto, y esa población tiene adopción cero
por definición (no puede tener saldo en Invesbot si no tiene productos).

Comparando solo entre clientes que **sí tienen productos**, que es la
comparación limpia:

| | Con estimador | Sin estimador | Razón |
|---|---|---|---|
| Adoptan | 12,08% (n=506.263) | 2,15% (n=23.207) | **5,6×** |

El hallazgo se sostiene y sigue siendo fuerte, pero la magnitud honesta es
5,6×. Se corrigió tras detectar el efecto de confusión.

**Qué se hizo con esos clientes**: no se imputó ningún valor y no se excluyó a
nadie. Se añadió una bandera explícita de "falta el dato" y el modelo la usa
como predictora. Un modelo entrenado para adivinar *quién* tiene el dato
faltante alcanza AUC 0,886 — la ausencia es altamente predecible y por lo tanto
informativa. Rellenarla con un promedio habría destruido esa señal.
            """)

    # -------------------------------------------------------------------- edad
    st.header("3. La edad: el pico está en la mitad de la vida laboral")
    izq2, der2 = st.columns([3, 2])
    with izq2:
        st.altair_chart(
            es.barras_tasa(tasas[tasas["variable"] == "grupo_edad"],
                           "categoria", "Edad", tasa_base, 190))
    with der2:
        es.respuesta(
            "La curva tiene forma de campana: sube hasta los 36-49 años "
            "(9,5%) y cae en los extremos. Los más jóvenes (3,3%) todavía no "
            "tienen excedente; los mayores de 65 (4,5%) ya salieron de la "
            "etapa de acumulación.",
            rotulo="Qué dice")

    # ------------------------------------------------------- género y vivienda
    st.header("¿Influyen el género y el tipo de vivienda?")

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Género")
        es.respuesta(
            "Sí hay diferencia descriptiva —las mujeres invierten un poco más "
            "(8,3% contra 5,7%)— pero es la variable con <b>menos</b> poder "
            "predictivo de todas las evaluadas. Y aun así <b>se excluyó del "
            "modelo a propósito</b>.",
            rotulo="Respuesta")
        es.cautela(
            "Se excluye por <b>idoneidad, no por falta de poder</b>. Si el "
            "género resultara predictivo, estaría reflejando una desigualdad "
            "histórica de acceso al ahorro y la inversión — no una señal que un "
            "modelo comercial deba aprender a explotar. Se conserva únicamente "
            "para poder auditar que el modelo no lo esté usando por vías "
            "indirectas."
        )
    with g2:
        st.subheader("Tipo de vivienda")
        st.altair_chart(
            es.barras_tasa(
                tasas[tasas["variable"] == "desc_tipo_de_vivienda"].dropna(
                    subset=["categoria"]),
                "categoria", "Vivienda", tasa_base, 150))
        es.cautela(
            "Sí influye, pero <b>no por lo que parece</b>. El 69% de la base "
            "no tiene ese dato, y quien no lo reporta tiene un patrimonio "
            "mediano de $3,9 millones contra $24 millones de quien sí lo "
            "reporta. La variable está midiendo, en buena parte, "
            "<b>profundidad de la relación con el banco</b> más que vivienda."
        )

    # ---------------------------------------------------------------- síntesis
    st.header("Entonces, ¿qué hace potencial a un cliente?")
    es.respuesta(
        "El perfil que el modelo premia es consistente y tiene sentido de "
        "negocio: <b>un cliente de segmento alto, en plena etapa de "
        "acumulación, con excedente mensual, que ya mueve varios productos con "
        "el banco y cuya plata circula por aquí</b>. Nada de eso es "
        "sorprendente — y que no lo sea es buena señal: significa que el "
        "modelo aprendió el negocio, no ruido.",
        rotulo="Síntesis")

    with es.detalle("Cómo se midió cada factor"):
        st.markdown(
            """
Cada variable se evaluó con **Information Value (IV)**, que mide cuánto separa
a adoptantes de no adoptantes, y con pruebas de significancia estadística que
descartan que la diferencia sea casualidad.

Las variables con más poder resultaron ser, en orden: número de productos que
tiene el cliente, saldo líquido total, antigüedad de la relación, y qué tan
reciente es su última actividad. Es decir: **relación con el banco por encima
de características demográficas**.

El segmento comercial tiene IV = 0,85 (fuerte). El género, IV = 0,039 (débil) —
otra razón por la que excluirlo no cuesta nada en desempeño.
            """)
