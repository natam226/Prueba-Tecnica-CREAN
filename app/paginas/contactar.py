"""Cuántos clientes contactar, a quiénes, y por qué a ese cliente en concreto."""
import altair as alt
import pandas as pd
import streamlit as st

from app import datos as dat
from app import estilo as es
from app import explicacion as exp


def render():
    tasa_base = dat.tasa_base()

    st.title("A quién contactar")
    st.markdown("**¿Cuántas llamadas hacer y en qué orden?**")

    es.respuesta(
        "Llamando al <b>10% mejor rankeado</b> —17.204 clientes— se alcanza a "
        "<b>más de la mitad de todos los que invertirían</b>, y 4 de cada 10 "
        "llamadas dan en el blanco. Eso es <b>5 veces mejor que llamar al "
        "azar</b>.<br><br>"
        "Dónde parar es una decisión de costo, y la tabla de abajo la vuelve "
        "explícita."
    )

    _curva_de_esfuerzo(tasa_base)
    st.divider()
    lista, base = _lista_de_contacto()
    if lista is None:
        return
    st.divider()
    _ficha_de_cliente(lista, base)


# ---------------------------------------------------------------------------
def _curva_de_esfuerzo(tasa_base: float):
    st.header("¿Hasta dónde conviene llamar?")
    curva = dat.csv("models/curva_precision_recall.csv")

    tabla = curva.assign(
        Esfuerzo=lambda d: d["top_pct"].map(lambda p: f"Top {p:.0%}"),
        Llamadas=lambda d: d["n_contactados"].map(es.miles),
        Aciertan=lambda d: d["precision"].map(lambda v: f"{v:.0%}"),
        Alcance=lambda d: d["recall"].map(lambda v: f"{v:.0%}"),
        Mejor_que_azar=lambda d: (d["precision"] / tasa_base).map(
            lambda v: f"{v:.1f}×"),
    )

    izq, der = st.columns([3, 2])
    with izq:
        largo = curva.melt(id_vars="top_pct",
                           value_vars=["precision", "recall"],
                           var_name="métrica", value_name="valor")
        largo["métrica"] = largo["métrica"].map({
            "precision": "De cada 100 llamadas, cuántas aciertan",
            "recall": "Qué % de los interesados alcanzo"})
        st.altair_chart(
            alt.Chart(largo).mark_line(point=True, size=3).encode(
                x=alt.X("top_pct:Q", title="Porcentaje de la base que se llama",
                        axis=alt.Axis(format=".0%")),
                y=alt.Y("valor:Q", title=None, axis=alt.Axis(format=".0%")),
                color=alt.Color("métrica:N", title=None,
                                scale=alt.Scale(range=[es.AZUL, es.VERDE]),
                                legend=alt.Legend(orient="bottom", columns=1)),
                tooltip=[alt.Tooltip("top_pct:Q", format=".0%", title="Esfuerzo"),
                         "métrica:N", alt.Tooltip("valor:Q", format=".1%")],
            ).properties(width="container", height=280))
    with der:
        st.dataframe(
            tabla[["Esfuerzo", "Llamadas", "Aciertan", "Alcance",
                   "Mejor_que_azar"]],
            hide_index=True, width="stretch",
            column_config={"Mejor_que_azar": st.column_config.TextColumn(
                "Mejor que azar")})
        es.respuesta(
            "Las dos curvas se cruzan: <b>llamar a más gente alcanza a más "
            "interesados pero desperdicia más llamadas</b>. Pasar del 10% al "
            "20% sube el alcance de 52% a 77%, pero la tasa de acierto cae de "
            "37% a 28%.",
            rotulo="El intercambio")

    es.nota(
        "<b>Esta es la tabla que convierte el modelo en una decisión.</b> Si "
        "una llamada cuesta poco, conviene ir al 20%. Si el equipo comercial "
        "es pequeño y cada contacto es caro, el 5% da 44% de acierto. La "
        "elección es del negocio; el modelo solo dice cuánto cuesta cada "
        "opción."
    )


# ---------------------------------------------------------------------------
def _lista_de_contacto():
    st.header("La lista")
    base = dat.base_clientes()

    f1, f2, f3 = st.columns(3)
    poblacion = f1.multiselect("Grupo de clientes",
                               sorted(base["poblacion"].unique()),
                               default=sorted(base["poblacion"].unique()))
    nivel = f2.multiselect("Nivel de prioridad",
                           sorted(base["nivel"].dropna().unique()),
                           default=["A"])
    segmentos = sorted(base["desc_segmento"].dropna().unique())
    segmento = f3.multiselect("Segmento comercial", segmentos, default=segmentos)
    solo_monto = st.checkbox("Solo clientes con monto estimado "
                             "(los que ya tienen algún producto de inversión)")

    sel = base[base["poblacion"].isin(poblacion)
               & base["nivel"].isin(nivel)
               & base["desc_segmento"].isin(segmento)]
    if solo_monto:
        sel = sel[sel["tiene_historial_inversion"] == 1]
    if sel.empty:
        st.warning("Ningún cliente cumple los filtros seleccionados.")
        return None, base

    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes seleccionados", es.miles(len(sel)))
    c2.metric("Dinero que podrían mover",
              es.cop(sel["monto_base_12m"].clip(lower=0).sum()))
    c3.metric("Con monto estimado", es.miles(sel["monto_base_12m"].notna().sum()))

    if (sel["poblacion"] == "sin_historial").any():
        es.cautela(
            "La selección incluye <b>clientes sin ningún producto</b>. Su "
            "puntaje mide <b>parecido</b> con quienes invierten, no una "
            "probabilidad validada. Sirve para explorar adquisición en frío; "
            "no para comprometer una tasa de conversión."
        )

    # `valor_referencia` significa cosas distintas según el grupo y sus escalas
    # no son comparables. Se ordena por percentil DENTRO de cada grupo, que es
    # la misma lógica con la que se construyen los niveles.
    sel = sel.assign(
        percentil_en_grupo=sel.groupby("poblacion")["valor_referencia"]
        .rank(method="first", pct=True))

    COLS = ["numero_id", "poblacion", "nivel", "percentil_en_grupo",
            "desc_segmento", "grupo_edad", "score", "modelo_usado",
            "monto_base_12m", "valor_esperado_12m"]
    lista = (sel[[c for c in COLS if c in sel.columns]]
             .sort_values("percentil_en_grupo", ascending=False))

    tope = st.number_input("Cuántos exportar", min_value=min(100, len(lista)),
                           max_value=len(lista),
                           value=min(5000, len(lista)), step=100)
    lista = lista.head(int(tope))

    st.dataframe(
        lista.head(150), hide_index=True, width="stretch", height=330,
        column_config={
            "numero_id": st.column_config.TextColumn("ID cliente"),
            "poblacion": st.column_config.TextColumn("Grupo"),
            "nivel": st.column_config.TextColumn("Nivel"),
            "percentil_en_grupo": st.column_config.ProgressColumn(
                "Posición en su grupo", format="%.3f",
                min_value=0.0, max_value=1.0),
            "desc_segmento": st.column_config.TextColumn("Segmento"),
            "grupo_edad": st.column_config.TextColumn("Edad"),
            "score": st.column_config.NumberColumn("Puntaje", format="%.4f"),
            "modelo_usado": st.column_config.TextColumn("Modelo"),
            "monto_base_12m": st.column_config.NumberColumn(
                "Monto 12m", format="%.0f"),
            "valor_esperado_12m": st.column_config.NumberColumn(
                "Valor esperado", format="%.0f"),
        })
    es.pie(f"Vista previa de 150 filas; la descarga trae {len(lista):,}.")

    st.download_button(
        "⬇  Descargar lista de contacto (CSV)",
        lista.to_csv(index=False).encode("utf-8-sig"),
        file_name="lista_contacto_crean.csv", mime="text/csv", type="primary")

    with es.detalle("Por qué se ordena por posición dentro del grupo"):
        st.markdown(
            """
Los tres grupos se rankean con escalas que **no son comparables entre sí**:
donde hay monto estimado se usa puntaje × monto; donde no lo hay, puntaje ×
capacidad de ahorro; y si tampoco hay capacidad, el puntaje solo.

Mezclarlos y ordenar por el valor crudo ponía arriba a clientes con puntaje de
0,0056 empujados por capacidades de ahorro poco creíbles: la base tiene **222
clientes con más de $1.000 millones anuales de capacidad de ahorro** y un
máximo de $108 billones, contra una mediana de $18 millones. Es un problema de
calidad en la fuente que estaba moldeando el orden en silencio.

Ordenar por **percentil dentro de cada grupo** es la misma lógica con la que se
construyen los niveles A/B/C/D, y hace que la lista mezclada intercale
honestamente lo mejor de cada grupo.
            """)
    return lista, base


# ---------------------------------------------------------------------------
def _ficha_de_cliente(lista, base):
    st.header("¿Y este cliente por qué?")
    es.respuesta(
        "Seleccione un cliente y verá qué características suyas se asocian con "
        "invertir, comparadas contra el cliente promedio que invierte y el que "
        "no. Es lo que un gestor necesita para preparar la llamada.",
        rotulo="Para qué sirve")

    try:
        woe_bins = dat.csv("eda/woe_por_bin.csv")
    except dat.ArtefactosFaltantes as falta:
        st.info(f"Esta sección necesita `{falta}`, que produce "
                "`notebooks/04_validacion_variables.ipynb`. La lista de arriba "
                "no depende de ese archivo.")
        return

    sugeridos = lista.head(20)["numero_id"].tolist()
    c_sel, c_txt = st.columns([2, 3])
    elegido = c_sel.selectbox("Elegir de los 20 primeros", sugeridos)
    escrito = c_txt.text_input("…o pegar un ID de cliente", value=elegido)
    cliente_id = (escrito or elegido).strip()

    features = dat.features_de(cliente_id)
    if features is None:
        st.warning(f"No existe ningún cliente con el identificador `{cliente_id}`.")
        return
    fila = base[base["numero_id"] == cliente_id]
    if fila.empty:
        st.warning("El cliente existe pero no está en la tabla de puntajes.")
        return
    fila = fila.iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Puntaje", f"{fila['score']:.4f}", f"nivel {fila['nivel']}")
    k2.metric("Grupo", str(fila["poblacion"]).replace("_", " "))
    k3.metric("Monto estimado 12m", es.cop(fila.get("monto_base_12m")))
    k4.metric("Segmento", str(fila.get("desc_segmento", "—")))

    evidencia = exp.evidencia_del_cliente(features, woe_bins)
    if evidencia.empty:
        st.info("No se pudo ubicar ninguna variable de este cliente en los "
                "tramos calculados.")
        return

    top = evidencia.head(10)
    izq, der = st.columns([3, 2])
    with izq:
        # Al gráfico solo se le pasan las columnas que usa. `valor_cliente`
        # mezcla números, texto y nulos, y Altair también serializa vía Arrow:
        # incluirla dispara el mismo fallo de conversión que la tabla.
        datos_grafico = top[["variable", "bin", "direccion", "woe"]]
        st.altair_chart(
            alt.Chart(datos_grafico).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("variable:N", sort="-x", title=None),
                # Se grafica -woe para que "hacia la derecha" signifique
                # a favor; con el signo crudo el gráfico se lee al revés.
                x=alt.X("a_favor:Q", title="← juega en contra   ·   juega a favor →"),
                color=alt.Color("direccion:N", title=None,
                                scale=alt.Scale(
                                    domain=["a favor", "en contra", "neutro"],
                                    range=[es.VERDE, es.TERRACOTA, es.GRIS])),
                tooltip=["variable:N", "bin:N", "direccion:N"],
            ).transform_calculate(a_favor="-datum.woe")
            .properties(width="container", height=300))
    with der:
        # `valor_cliente` mezcla números, texto y nulos: un saldo junto a
        # "preferencial" y junto a un None legítimo (la variable cae en el
        # tramo "Sin dato"). Arrow no serializa columnas de tipo mixto, y
        # `astype(str)` no basta porque en pandas 3 deja los nulos como float.
        # Se formatea cada valor a texto, con guion para los nulos.
        tabla_evidencia = top[["variable", "valor_cliente", "direccion"]].assign(
            valor_cliente=lambda d: d["valor_cliente"].map(
                lambda v: "—" if pd.isna(v) else str(v)))
        st.dataframe(tabla_evidencia,
                     hide_index=True, width="stretch", height=300,
                     column_config={
                         "variable": st.column_config.TextColumn("Característica"),
                         "valor_cliente": st.column_config.TextColumn("Su valor"),
                         "direccion": st.column_config.TextColumn("Juega"),
                     })

    numericas = tuple(v for v in top["variable"]
                      if pd.api.types.is_number(features[v]))
    if numericas:
        st.subheader("Comparado contra quién")
        medianas = dat.medianas_por_etiqueta(numericas)
        comparacion = medianas.assign(
            valor_cliente=lambda d: d["variable"].map(lambda v: features[v]))
        st.dataframe(
            comparacion[["variable", "valor_cliente", "mediana_adoptantes",
                         "mediana_no_adoptantes"]],
            hide_index=True, width="stretch",
            column_config={
                "variable": st.column_config.TextColumn("Característica"),
                "valor_cliente": st.column_config.NumberColumn(
                    "Este cliente", format="%.2f"),
                "mediana_adoptantes": st.column_config.NumberColumn(
                    "Típico de quien invierte", format="%.2f"),
                "mediana_no_adoptantes": st.column_config.NumberColumn(
                    "Típico de quien no", format="%.2f"),
            })

    es.cautela(
        "<b>Esto explica al cliente, no explica al modelo.</b> Cada barra mide "
        "cuánto se asocia esa característica con invertir <i>mirada por "
        "separado</i> en toda la base. El modelo combina las variables entre "
        "sí de formas que este desglose no captura. Sirve para preparar una "
        "conversación comercial; no para auditar la decisión del modelo."
    )
