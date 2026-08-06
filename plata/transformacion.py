# plata/transformacion.py
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite
from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual

COLS_FINANCIERAS = ["ingresos_mensuales", "total_egresos_mensuales", "total_activos", "total_pasivos", "total_patrimonio"]

MAPA_PRODUCTO_SLUG = {
    "CUENTA DE AHORRO": "cuenta_ahorro",
    "CUENTA DE CORRIENTE": "cuenta_corriente",
    "BOLSILLOS": "bolsillos",
    "FIDUCUENTA": "fiducuenta",
    "CDT": "cdt",
    "INVERSION_VIRTUAL": "inversion_virtual",
    "INVESBOT": "invesbot",
}


def limpiar_clientes():
    df = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    df = df.drop_duplicates(subset="numero_id", keep="first")
    df["sin_dato_financiero"] = df[COLS_FINANCIERAS].isnull().any(axis=1)
    df["capacidad_ahorro"] = df["ingresos_mensuales"] - df["total_egresos_mensuales"]
    escribir_tabla_sqlite(df, config.PLATA_DB, "clientes_plata")
    return df


def transformar_aho_cte():
    df = leer_tabla_sqlite(config.BRONCE_DB, "crean_aho_cte")
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(df, group_cols=["numero_id", "producto"], meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "aho_cte_plata")
    return resultado


if __name__ == "__main__":
    df = limpiar_clientes()
    print(f"clientes_plata: {len(df)} filas, {df['sin_dato_financiero'].sum()} con sin_dato_financiero")
    aho = transformar_aho_cte()
    print(f"aho_cte_plata: {len(aho)} filas, productos={sorted(aho['producto'].unique())}")
