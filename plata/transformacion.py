# plata/transformacion.py
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite
from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual
from src.fecha_corte import calcular_fecha_corte

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
