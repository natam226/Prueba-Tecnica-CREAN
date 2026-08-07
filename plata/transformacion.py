# plata/transformacion.py
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite
from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual
from src.fecha_corte import calcular_fecha_corte
from src.panel_mensual import construir_panel_mensual, primer_mes_por_grupo

FECHA_CORTE = None  # se resuelve en tiempo de ejecución, ver _fecha_corte()


def _fecha_corte():
    global FECHA_CORTE
    if FECHA_CORTE is None:
        FECHA_CORTE = calcular_fecha_corte()
    return FECHA_CORTE


COLS_FINANCIERAS = config.COLS_FINANCIERAS

MAPA_PRODUCTO_SLUG = {
    "CUENTA DE AHORRO": "cuenta_ahorro",
    "CUENTA DE CORRIENTE": "cuenta_corriente",
    "BOLSILLOS": "bolsillos",
    "FIDUCUENTA": "fiducuenta",
    "CDT": "cdt",
    "INVERSION_VIRTUAL": "inversion_virtual",
    "INVESBOT": "invesbot",
}

FUENTES_PRODUCTO_UNICO = [
    ("crean_bolsillos", "bolsillos_plata"),
    ("crean_fiducuenta", "fiducuenta_plata"),
    ("invesbot", "invesbot_plata"),
]


def limpiar_clientes():
    df = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    df = df.drop_duplicates(subset="numero_id", keep="first")
    # `any`: bandera descriptiva conservadora (Pregunta Abierta #3)
    df["sin_dato_financiero"] = df[COLS_FINANCIERAS].isnull().any(axis=1)
    # `all`: "ninguna señal financiera", único insumo válido para la exclusión de SPEC_V2 §2
    df["sin_dato_financiero_total"] = df[COLS_FINANCIERAS].isnull().all(axis=1)
    df["capacidad_ahorro"] = df["ingresos_mensuales"] - df["total_egresos_mensuales"]
    escribir_tabla_sqlite(df, config.PLATA_DB, "clientes_plata")
    return df


def transformar_aho_cte():
    tabla_bronce = "crean_aho_cte"
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    assert df["producto"].notna().all(), f"valores de producto sin mapear en {tabla_bronce}"
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id", "producto"], fecha_corte=_fecha_corte(),
        meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "aho_cte_plata")
    return resultado


def transformar_producto_unico(tabla_bronce, tabla_plata_destino):
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    assert df["producto"].notna().all(), f"valores de producto sin mapear en {tabla_bronce}"
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id", "producto"], fecha_corte=_fecha_corte(),
        meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, tabla_plata_destino)
    return resultado


def transformar_cdt_inversion_virtual():
    tabla_bronce = "crean_inv_virtual_cdt"
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    df["producto"] = df["producto"].apply(normalizar_producto_inv_virtual).map(MAPA_PRODUCTO_SLUG)
    assert df["producto"].notna().all(), f"valores de producto sin mapear en {tabla_bronce}"
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id", "producto"], fecha_corte=_fecha_corte(),
        meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "cdt_inversion_virtual_plata")
    return resultado


# (tabla_bronce, normalizar_inv_virtual) por cada una de las 5 fuentes de saldo
FUENTES_SALDO = [
    ("crean_aho_cte", False),
    ("crean_bolsillos", False),
    ("crean_fiducuenta", False),
    ("invesbot", False),
    ("crean_inv_virtual_cdt", True),   # requiere normalizar_producto_inv_virtual
]


def _leer_fuente_saldo(tabla_bronce, normalizar_inv_virtual):
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    if normalizar_inv_virtual:
        df["producto"] = df["producto"].apply(normalizar_producto_inv_virtual)
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    assert df["producto"].notna().all(), f"valores de producto sin mapear en {tabla_bronce}"
    return df[["numero_id", "producto", "fecha", "saldo"]]


def construir_saldos_mensual():
    """Panel cliente-producto-mes con forward fill (SPEC_V2 §6.3.1 y §8).

    D4 CAMBIA la propuesta provisional del plan v1 ("cada fuente contra su
    propio máximo"): las 5 fuentes se regularizan contra el MISMO `mes_max`,
    derivado de `FECHA_CORTE` global (src/fecha_corte.py, memoizada aquí en
    `_fecha_corte()`).
    Con cortes por fuente cada cliente-producto queda medido en un momento
    distinto; con un `mes_max` compartido, ninguna fuente aporta meses que
    las demás no puedan ver.

    `construir_panel_mensual` bucketea a granularidad de MES (toma la última
    fila dentro de cada mes). `FECHA_CORTE` es una fecha exacta (día), y las
    5 fuentes terminan en días distintos dentro de ese mismo mes de corte
    (p.ej. bolsillos el día 1, CDT el día 30). Sin un filtro a nivel de día
    ANTES de bucketear, el mes de corte terminaría representando "lo último
    visto por cada fuente" en vez de "lo último visto al mismo instante para
    todas" — exactamente lo que D4 prohíbe. Por eso se trunca cada fuente a
    `fecha <= FECHA_CORTE` (día exacto, igual que `agregar_serie_saldo`) antes
    de pasarla a `construir_panel_mensual`.
    """
    fecha_corte = _fecha_corte()
    paneles = []
    for tabla, normalizar in FUENTES_SALDO:
        df = _leer_fuente_saldo(tabla, normalizar)
        df = df[pd.to_datetime(df["fecha"]) <= fecha_corte]
        panel = construir_panel_mensual(
            df, group_cols=["numero_id", "producto"], mes_max=fecha_corte)
        paneles.append(panel)
    resultado = pd.concat(paneles, ignore_index=True)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "saldos_mensual_plata")
    return resultado


def construir_primer_registro():
    """Primer mes con registro del cliente en fuentes de saldo NO-etiqueta.
    Insumo de `antiguedad_relacion_meses` (SPEC_V2 §5, D8).

    D8 AMENDADA (corrección de fuga; ver la clave
    `fuga_recencia_antiguedad` en el log de decisiones):
    la redacción original decía "primer registro del cliente en CUALQUIER
    fuente". Ese MIN incluía a Invesbot/Inversión Virtual
    (`config.PRODUCTOS_ETIQUETA`), los dos productos que DEFINEN
    `etiqueta_adopcion` -- para ~32% de los adoptantes, el registro más
    antiguo del cliente estaba precisamente en uno de esos dos productos, así
    que `antiguedad_relacion_meses` terminaba siendo una función directa de
    la etiqueta en vez de una medida genuina de antigüedad. Se filtran las
    filas de producto-etiqueta ANTES de tomar el mínimo por cliente (no la
    fuente completa: `crean_inv_virtual_cdt` mezcla CDT -- no-etiqueta -- con
    Inversión Virtual -- etiqueta -- en la misma tabla bronce). Un cliente
    cuyo ÚNICO registro esté en una fuente-etiqueta queda deliberadamente
    fuera de `primer_registro_plata`: no hay señal de antigüedad no-etiqueta
    para él bajo esta definición.
    """
    minimos = []
    for tabla, normalizar in FUENTES_SALDO:
        df = _leer_fuente_saldo(tabla, normalizar)
        df = df[~df["producto"].isin(config.PRODUCTOS_ETIQUETA)]
        minimos.append(primer_mes_por_grupo(df, group_cols=["numero_id"]))
    resultado = (
        pd.concat(minimos, ignore_index=True)
        .groupby("numero_id", as_index=False)["primer_mes"].min()
    )
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "primer_registro_plata")
    return resultado


def _stats_corte_fuente(df, fecha_corte):
    """Cuántas filas y grupos cliente-producto de UNA fuente quedan fuera del
    corte global (D4: "Registrar cuántos registros quedan fuera por fuente al
    aplicar el corte global"). `panel_mensual` es genérico y no reporta esto
    porque no conoce la procedencia de cada fila; este es el call site que sí
    la conoce.

    Comparación a nivel de DÍA (no de mes): es la misma granularidad que
    `construir_saldos_mensual` aplica ahora antes de bucketear (ver su
    docstring) y la misma que usa `agregar_serie_saldo`. Con corte a nivel de
    mes, una fuente con datos hasta el día 30 del mes de corte parecía no
    perder nada aunque en la práctica aportaba hasta 29 días de actividad que
    otras fuentes, cortadas antes en ese mismo mes, no tenían — justo lo que
    D4 busca evitar.
    """
    d = df.copy()
    d["fecha"] = pd.to_datetime(d["fecha"])
    posteriores = d["fecha"] > fecha_corte

    grupos_totales = d.groupby(["numero_id", "producto"]).ngroups
    grupos_con_dato_valido = d.loc[~posteriores].groupby(["numero_id", "producto"]).ngroups

    return {
        "filas_totales": len(d),
        "filas_posteriores_al_corte": int(posteriores.sum()),
        "grupos_totales": grupos_totales,
        # grupo sin NINGUNA fila <= fecha_corte: `construir_panel_mensual` no
        # tiene nada que bucketear para él y lo omite por completo (0 filas).
        "grupos_omitidos_por_corte": grupos_totales - grupos_con_dato_valido,
        "fecha_max_fuente": d["fecha"].max(),
    }


def reportar_recorte_por_fuente():
    """D4: por cada una de las 5 fuentes de saldo, cuántas filas quedan por
    encima del corte global — a nivel de día — y no se usan, cuántos grupos
    cliente-producto se omiten por completo del panel (ninguna fila suya cae
    en o antes del corte), y el día máximo real de cada fuente frente a
    `FECHA_CORTE`, para que se vea de un vistazo el desfase que el truncado
    por día corrige.
    """
    fecha_corte = _fecha_corte()
    return {
        tabla: _stats_corte_fuente(_leer_fuente_saldo(tabla, normalizar), fecha_corte)
        for tabla, normalizar in FUENTES_SALDO
    }


def transformar_estimador_ingresos():
    df = leer_tabla_sqlite(config.BRONCE_DB, "estimador_ing")[["numero_id", "estimador_ingreso"]]
    df["tiene_estimador_ingreso"] = True
    escribir_tabla_sqlite(df, config.PLATA_DB, "estimador_ingresos_plata")
    return df


if __name__ == "__main__":
    df = limpiar_clientes()
    print(f"clientes_plata: {len(df)} filas, {df['sin_dato_financiero'].sum()} con sin_dato_financiero")
    aho = transformar_aho_cte()
    print(f"aho_cte_plata: {len(aho)} filas, productos={sorted(aho['producto'].unique())}")
    for tabla_bronce, tabla_plata_destino in FUENTES_PRODUCTO_UNICO:
        resultado = transformar_producto_unico(tabla_bronce, tabla_plata_destino)
        print(f"{tabla_plata_destino}: {len(resultado)} filas")
    cdt_iv = transformar_cdt_inversion_virtual()
    print(f"cdt_inversion_virtual_plata: {len(cdt_iv)} filas, productos={sorted(cdt_iv['producto'].unique())}")
    est = transformar_estimador_ingresos()
    print(f"estimador_ingresos_plata: {len(est)} filas")

    mensual = construir_saldos_mensual()
    print(f"saldos_mensual_plata: {len(mensual)} filas, "
          f"{mensual['mes'].min()} -> {mensual['mes'].max()}")
    primer = construir_primer_registro()
    print(f"primer_registro_plata: {len(primer)} filas")

    # D4: registrar cuántos registros quedan fuera por fuente al aplicar el corte global
    fecha_corte = _fecha_corte()
    print(f"D4 - corte global aplicado (FECHA_CORTE={fecha_corte.date()}), por fuente:")
    for tabla, stats in reportar_recorte_por_fuente().items():
        desfase_dias = (stats["fecha_max_fuente"] - fecha_corte).days
        print(
            f"  {tabla}: max real={stats['fecha_max_fuente'].date()} "
            f"(+{desfase_dias}d vs corte) -> "
            f"{stats['filas_posteriores_al_corte']}/{stats['filas_totales']} filas "
            f"posteriores al corte descartadas, "
            f"{stats['grupos_omitidos_por_corte']}/{stats['grupos_totales']} "
            f"grupos cliente-producto omitidos por completo"
        )
