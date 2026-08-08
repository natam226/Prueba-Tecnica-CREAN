"""Modelo de datos, aporte a los procesos de CREAN y esquema de operación.

Los diagramas se dibujan con Graphviz, que Streamlit renderiza de forma nativa
a partir de una cadena DOT, sin dependencias adicionales.
"""
import pandas as pd
import streamlit as st

from app import estilo as es

# Paleta compartida con el resto del tablero, en el formato que espera DOT.
_FUENTE = 'fontname="Helvetica" fontsize=10'

MODELO_DATOS = f"""
digraph {{
  rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.65;
  node [shape=box style="rounded,filled" {_FUENTE} color="#7C8B96"];
  edge [color="#7C8B96" arrowsize=0.7];

  fuentes [label="7 fuentes\\noperativas\\n6,6 M filas" fillcolor="#FFFFFF"];
  bronce  [label="BRONCE\\nIngesta cruda\\n+ calidad" fillcolor="#F5E9D7" color="#A97142"];
  plata   [label="PLATA\\nLimpieza y\\nagregación\\n9,87 M filas" fillcolor="#ECEFF1"];
  oro     [label="ORO\\n1 fila por cliente\\n860.223" fillcolor="#FBF3DC" color="#C99A2E"];
  score   [label="Puntajes y montos\\npor cliente" fillcolor="#E6F2EC" color="#2E8B57"];
  salida  [label="Tablero · Power BI\\n· Lista CSV" fillcolor="#E8F1F5" color="#1F6F8B"];

  fuentes -> bronce -> plata -> oro -> score -> salida;
}}
"""

CICLO = f"""
digraph {{
  rankdir=LR; bgcolor="transparent"; nodesep=0.3; ranksep=0.6;
  node [shape=box style="rounded,filled" {_FUENTE} color="#7C8B96"];
  edge [color="#7C8B96" arrowsize=0.7];

  mensual [label="MENSUAL\\nRefrescar puntajes,\\nmontos y auditoría" fillcolor="#E8F1F5" color="#1F6F8B"];
  trim    [label="TRIMESTRAL\\nReentrenar y\\ncomparar" fillcolor="#FBF3DC" color="#C99A2E"];
  evento  [label="POR EVENTO\\nDeriva, caída de\\ndesempeño, alerta" fillcolor="#F8E3E0" color="#B4453A"];
  decide  [label="¿Mejora el\\nmodelo nuevo?" shape=diamond fillcolor="#FFFFFF"];
  promo   [label="Se promueve" fillcolor="#E6F2EC" color="#2E8B57"];
  queda   [label="Se conserva\\nel vigente" fillcolor="#FFFFFF"];

  mensual -> trim; trim -> decide;
  decide -> promo [label="sí" {_FUENTE}];
  decide -> queda [label="no" {_FUENTE}];
  evento -> trim [label="adelanta" style=dashed {_FUENTE}];
}}
"""


def render():
    st.title("Cómo opera dentro de CREAN")
    st.markdown("**¿De dónde salen los datos, a qué procesos aportan y cómo se mantiene?**")

    es.respuesta(
        "La solución no es un análisis que se entrega y se archiva: es un "
        "<b>proceso mensual</b> que integra siete fuentes del banco, produce "
        "una lista priorizada y una cifra de oportunidad, y se vigila a sí "
        "misma. Aporta directamente a cuatro de los siete procesos de CREAN."
    )

    # ------------------------------------------------------- modelo de datos
    st.header("1. El modelo de datos")
    es.respuesta(
        "Siete fuentes que hoy viven separadas se integran en tres capas hasta "
        "producir <b>una sola fila por cliente</b>. Cada capa tiene un nivel de "
        "detalle declarado y verificado automáticamente, así que siempre se "
        "puede rastrear una cifra final hasta el dato original.",
        rotulo="Para qué sirve")

    st.graphviz_chart(MODELO_DATOS, width="stretch")

    st.dataframe(pd.DataFrame([
        {"Capa": "Bronce", "Qué contiene": "Las 7 fuentes tal como llegaron",
         "Nivel de detalle": "El de origen",
         "Por qué existe": "Permite auditar contra el dato original"},
        {"Capa": "Plata", "Qué contiene": "Datos limpios y agregados",
         "Nivel de detalle": "Cliente-producto y cliente-mes",
         "Por qué existe": "Deduplica y unifica el corte temporal"},
        {"Capa": "Oro", "Qué contiene": "Vista analítica + esquema estrella",
         "Nivel de detalle": "Una fila por cliente",
         "Por qué existe": "Es sobre lo que se modela y se consume"},
    ]), hide_index=True, width="stretch")

    with es.detalle("Decisiones de integración que valen la pena mencionar"):
        st.markdown(
            """
**Corte temporal único.** Las cinco fuentes de saldo se recortan contra la
misma fecha. La alternativa —cada fuente contra su propio máximo— dejaría a
cada cliente-producto medido en un momento distinto, y "saldo actual"
significaría cosas diferentes según el producto.

**Relleno hacia adelante con marca.** Un saldo no observado en un mes no es
cero: es el último saldo conocido. Se arrastra, pero cada fila lleva una marca
que distingue el dato real del arrastrado, y las variables que exigen
observación real —como la volatilidad— solo cuentan meses efectivamente
observados.

**Deduplicación verificada.** La fuente de clientes trae 860.231 filas con
860.223 identificadores únicos. Una prueba automática verifica que la capa oro
tenga exactamente una fila por cliente.

**Identificadores como texto.** `numero_id` llega a ±9,2 × 10¹⁸, muy por encima
de lo que una hoja de cálculo representa con exactitud. Se exporta como texto
para que ninguna herramienta le cambie los últimos dígitos en silencio.
            """)

    # --------------------------------------------------------- procesos CREAN
    st.header("2. A qué procesos de CREAN aporta")
    es.respuesta(
        "A cuatro de forma directa y a dos parcialmente. Al séptimo "
        "—conciliación contable— <b>no aporta nada</b>, y decirlo es más útil "
        "que forzar el encaje.",
        rotulo="Respuesta")

    st.dataframe(pd.DataFrame([
        {"Proceso CREAN": "Afiliar / Desafiliar al servicio", "Aporte": "Directo",
         "Cómo": "Lista priorizada para afiliar · 40.137 clientes en riesgo de retiro para retener"},
        {"Proceso CREAN": "Administrar información", "Aporte": "Directo",
         "Cómo": "El pipeline es el ciclo de vida del dato: ingesta, calidad, trazabilidad"},
        {"Proceso CREAN": "Monitorear el servicio", "Aporte": "Directo",
         "Cómo": "Controles de fuga, sesgo y deriva incluidos en la solución"},
        {"Proceso CREAN": "Gestionar el uso del servicio", "Aporte": "Directo",
         "Cómo": "309.928 clientes con productos que nunca han invertido: uso no realizado"},
        {"Proceso CREAN": "Gestionar ingresos y gastos", "Aporte": "Parcial",
         "Cómo": "Entrega volumen potencial; no modela la monetización"},
        {"Proceso CREAN": "Administrar el servicio", "Aporte": "Parcial",
         "Cómo": "Define un ANS implícito de entrega mensual de la lista"},
        {"Proceso CREAN": "Conciliar transacciones y contabilidad", "Aporte": "No aplica",
         "Cómo": "Es integridad contable posterior al hecho; esto es predictivo y previo"},
    ]), hide_index=True, width="stretch")

    es.respuesta(
        "El encaje más fuerte es <b>Afiliar / Desafiliar</b>, y se sirve por "
        "los dos lados. La lista priorizada alimenta la afiliación. Y los "
        "<b>40.137 clientes que el modelo proyecta desinvirtiendo</b> alimentan "
        "el lado contrario: una base de retención con nombre y cédula que salió "
        "del mismo análisis sin costo adicional y que nadie estaba mirando.",
        rotulo="El hallazgo que nadie pidió")

    # ------------------------------------------------------------- operación
    st.header("3. Cómo se mantiene viva")
    es.respuesta(
        "Tres ritmos distintos, porque no todo cambia a la misma velocidad: "
        "los resultados se refrescan <b>cada mes</b>, el modelo se reentrena "
        "<b>cada trimestre</b>, y ciertos eventos pueden adelantar ese "
        "reentrenamiento.",
        rotulo="En corto")

    st.graphviz_chart(CICLO, width="stretch")

    es.nota(
        "<b>Por qué mensual y no diario:</b> el nivel de detalle útil del dato "
        "es el mes. Correrlo a diario movería 9,9 millones de filas sin "
        "producir información nueva.<br>"
        "<b>Por qué el reentrenamiento es trimestral:</b> la definición actual "
        "de adoptante se mueve lento — un cliente no entra y sale de «tiene "
        "saldo en Invesbot» cada semana. Reentrenar más seguido añadiría "
        "variabilidad, no señal."
    )

    st.subheader("Qué se vigila y quién responde")
    st.dataframe(pd.DataFrame([
        {"Qué se vigila": "Desempeño del modelo", "Alerta si": "Cae más de 0,05",
         "Cada": "Mes", "Responsable": "Analítica"},
        {"Qué se vigila": "Sospecha de fuga", "Alerta si": "El AUC supera 0,95",
         "Cada": "Entrenamiento", "Responsable": "Analítica"},
        {"Qué se vigila": "Deriva de las variables", "Alerta si": "Cambia la distribución",
         "Cada": "Mes", "Responsable": "Analítica"},
        {"Qué se vigila": "Impacto dispar", "Alerta si": "Razón menor a 0,80",
         "Cada": "Mes", "Responsable": "Riesgo / Cumplimiento"},
        {"Qué se vigila": "Reconstrucción del género", "Alerta si": "Supera 0,70",
         "Cada": "Trimestre", "Responsable": "Riesgo / Cumplimiento"},
        {"Qué se vigila": "Tasa de captura real vs asumida", "Alerta si": "Se desvía más de 10 puntos",
         "Cada": "Mes tras el lanzamiento", "Responsable": "CREAN / Producto"},
    ]), hide_index=True, width="stretch")

    es.cautela(
        "El último indicador es el más importante y <b>hoy no se puede "
        "medir</b>. La tasa de captura sostiene toda la cifra de oportunidad y "
        "solo se vuelve observable cuando la App esté en producción. El primer "
        "mes con datos reales convierte ese supuesto en una medición, y es la "
        "primera corrección que habrá que hacer."
    )

    # ------------------------------------------------------------- evolución
    st.header("4. Qué mejora sola el día del lanzamiento")
    es.respuesta(
        "La definición actual de «adoptante» es un sustituto que <b>caduca</b>. "
        "El día que la App salga habrá adopciones reales, y eso desbloquea "
        "tres cosas de golpe sin trabajo adicional de modelado.",
        rotulo="El argumento para empezar ya")

    c1, c2, c3 = st.columns(3)
    c1.markdown(
        "**La etiqueta se vuelve real**\n\nEl modelo pasa a predecir "
        "exactamente lo que importa, en vez de algo parecido.")
    c2.markdown(
        "**330.753 clientes se vuelven modelables**\n\nHoy reciben un puntaje "
        "de parecido porque en ese grupo no hay ni un solo adoptante. Cuando "
        "aparezcan, pasa a ser probabilidad validada.")
    c3.markdown(
        "**La tasa de captura se mide**\n\nDeja de ser un supuesto para "
        "convertirse en un dato, y la cifra de oportunidad se vuelve firme.")

    es.respuesta(
        "Por eso conviene operarla desde ya: no es un modelo terminado, es un "
        "modelo que <b>empieza a aprender de verdad</b> en el momento en que "
        "el producto entra al mercado.",
        rotulo="Conclusión")
