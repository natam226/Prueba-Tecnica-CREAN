# plata/transformacion.py
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

COLS_FINANCIERAS = ["ingresos_mensuales", "total_egresos_mensuales", "total_activos", "total_pasivos", "total_patrimonio"]


def limpiar_clientes():
    df = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    df = df.drop_duplicates(subset="numero_id", keep="first")
    df["sin_dato_financiero"] = df[COLS_FINANCIERAS].isnull().any(axis=1)
    df["capacidad_ahorro"] = df["ingresos_mensuales"] - df["total_egresos_mensuales"]
    escribir_tabla_sqlite(df, config.PLATA_DB, "clientes_plata")
    return df


if __name__ == "__main__":
    df = limpiar_clientes()
    print(f"clientes_plata: {len(df)} filas, {df['sin_dato_financiero'].sum()} con sin_dato_financiero")
