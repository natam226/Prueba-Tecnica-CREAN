"""Qué se asumió, qué sesgos se controlaron, y qué aportó cada control."""
import streamlit as st

import config
from app import datos as dat
from app import estilo as es


def render():
    st.title("Supuestos y sesgos")
    st.markdown("**¿Qué asumimos, qué controlamos y qué encontramos?**")

    es.respuesta(
        "Todo modelo descansa sobre supuestos. La diferencia está en si se "
        "declaran o se esconden.<br><br>"
        "Aquí están los seis que sostienen esta solución, los controles que se "
        "pusieron para vigilarlos, y —lo más importante— <b>los tres problemas "
        "reales que esos controles encontraron</b> antes de que llegaran a "
        "producción."
    )

    # ------------------------------------------------------ lo que encontraron
    st.header("Los controles no son decorativos: encontraron cosas")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Fuga de información")
        st.metric("AUC antes", "0,950", "el control se disparó",
                  delta_color="inverse")
        st.metric("AUC real", "0,894", "después de corregir")
    with c2:
        st.subheader("Sesgo por dato faltante")
        st.metric("Diferencia aparente", "19×", "estaba confundida",
                  delta_color="inverse")
        st.metric("Diferencia real", "5,6×", "comparando lo comparable")
    with c3:
        st.subheader("Rango de oportunidad")
        st.metric("Banda estadística", "±498%", "inservible",
                  delta_color="inverse")
        st.metric("Reemplazada por", "escenarios", "supuesto declarado")

    es.respuesta(
        "El caso más grave fue el primero. El sistema tiene una regla: <b>si el "
        "modelo acierta demasiado, algo está mal</b>. Se disparó con un AUC de "
        "0,950 y la investigación encontró que tres variables estaban mirando, "
        "indirectamente, la respuesta que debían predecir.<br><br>"
        "Sin ese control la solución se habría entregado prometiendo un "
        "desempeño que no existía, y habría fallado en producción justo sobre "
        "los clientes que más importan: los que aún no adoptaron.",
        rotulo="Por qué esto vende la solución")

    with es.detalle("Qué era exactamente la fuga y cómo se comprobó que se cerró"):
        st.markdown(
            """
Tres variables —hace cuánto se registró el último dato del cliente, si tiene
dato reciente, y su antigüedad— se calculaban agregando sobre **las siete
fuentes de producto, incluidas las dos que definen quién es adoptante**.

La consecuencia es sutil: para un adoptante, "hace cuánto se registró su último
dato" era muchas veces "hace cuánto se registró su saldo de Invesbot", es
decir, una pista directa de la respuesta. Medido: el dato extremo lo aportaba un
producto-etiqueta en el **31-32% de los adoptantes** contra el **0,02-0,06% de
los no adoptantes**. Las dos variables eran las número 1 y 2 en importancia.

Se redefinieron sobre las cinco fuentes que **no** definen la etiqueta:

| Versión | AUC |
|---|---|
| Con fuga | 0,9497 |
| Corregida | **0,8942** |
| Eliminando las variables por completo | 0,8941 |

Que la versión corregida y la versión sin las variables den prácticamente lo
mismo **es la prueba de que la fuga se cerró**. Si quedara contaminación, la
corregida seguiría estando por encima.
            """)

    # --------------------------------------------------------------- sesgo
    st.header("¿El modelo discrimina?")
    sesgo = dat.csv("powerbi/fact_auditoria_sesgo.csv")

    es.respuesta(
        "<b>No de forma evidente, pero hay una señal que hay que vigilar.</b> "
        "El género se sacó del modelo, pero sacarlo no basta: si el resto de "
        "variables permiten reconstruirlo, el sesgo entra por la puerta de "
        "atrás. Lo medimos y da <b>0,625</b> en una escala donde 0,5 es «no se "
        "puede reconstruir» y 1,0 es «se reconstruye perfectamente». Eso es "
        "<b>moderado</b>: se documenta y se vigila, no se ignora ni se "
        "sobrerreacciona."
    )

    if "auc_proxy_genero" in sesgo.columns and not sesgo.empty:
        auc_proxy = float(sesgo["auc_proxy_genero"].iloc[0])
        c1, c2 = st.columns([1, 3])
        c1.metric("Reconstrucción del género", f"{auc_proxy:.3f}",
                  str(sesgo["interpretacion_proxy_genero"].iloc[0]))
        with c2:
            es.nota(
                "Las variables que más permiten reconstruir el género son "
                "saldo invertido, estimador de ingresos e ingresos mensuales. "
                "Es decir, el efecto opera a través de <b>capacidad "
                "económica</b> — coherente con brechas de ingreso "
                "documentadas, no con un sesgo que el modelo haya inventado. "
                f"La banda de alerta empieza en "
                f"{config.UMBRAL_AUC_PROXY_SUSTANCIAL}."
            )

    with es.detalle("Regla del 80% por grupo protegido"):
        es.nota(
            "Compara qué porcentaje de cada grupo llega a nivel A contra el "
            "grupo mejor tratado. Por debajo de 0,80 hay indicio de impacto "
            "dispar y corresponde revisar antes de operar la lista."
        )
        st.dataframe(sesgo, hide_index=True, width="stretch")
        es.cautela(
            "<b>La razón sale 0,00 en todos los grupos, pero es un "
            "artefacto.</b> El grupo «Sin dato» de género tiene 93 clientes y "
            "tasa de selección cero, y arrastra el cociente. Entre femenino "
            "(26,7%) y masculino (23,0%) la razón real es <b>0,86, que sí "
            "cumple</b>. Hay que leer las tasas columna por columna antes de "
            "concluir."
        )

    # ------------------------------------------------------------- supuestos
    st.header("Los seis supuestos, en lenguaje llano")
    st.markdown(
        """
| Supuesto | Qué significa si falla |
|---|---|
| **«Adoptante» = tiene Invesbot o Inversión Virtual** | Si la App resulta muy distinta a esos productos, el modelo está prediciendo algo adyacente |
| **La tasa de captura se elige, no se mide** | La cifra de oportunidad se mueve proporcionalmente |
| **El futuro se parece al pasado reciente** | Se proyectan 12 meses con 13 de historia; un cambio de ciclo lo invalida |
| **La ausencia de dato es informativa** | Se modela como señal, no se rellena. Si el vacío fuera aleatorio, se estaría añadiendo ruido |
| **Los niveles no se comparan entre grupos** | Cada A es el 25% superior del suyo; fundirlos en una lista sin avisar mezcla cosas distintas |
| **El puntaje de quien no tiene productos es parecido, no probabilidad** | Prometer conversión sobre ese grupo sería prometer algo no validado |
        """)

    es.respuesta(
        "Ninguno de estos supuestos es un defecto: son las condiciones bajo "
        "las cuales la solución es válida. Declararlos permite que el negocio "
        "discuta el que le parezca discutible —normalmente la tasa de "
        "captura— en vez de aceptar o rechazar la cifra entera a ciegas.",
        rotulo="Para qué sirve declararlos")

    with es.detalle("Registro completo de decisiones"):
        es.nota(
            "Cada decisión analítica quedó registrada con su motivo y su "
            "evidencia medida, en cada corrida del pipeline. Es la trazabilidad "
            "que permite reconstruir por qué una cifra es lo que es.")
        try:
            st.dataframe(dat.csv("decisiones/log_decisiones.csv"),
                         hide_index=True, width="stretch", height=320)
        except dat.ArtefactosFaltantes:
            st.info("El registro se genera al ejecutar los notebooks.")
