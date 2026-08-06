# oro/construir_cliente_features.py
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

PRODUCTOS = ["cuenta_ahorro", "cuenta_corriente", "bolsillos", "fiducuenta", "cdt", "inversion_virtual", "invesbot"]

TABLAS_PRODUCTO = {
    "cuenta_ahorro": "aho_cte_plata",
    "cuenta_corriente": "aho_cte_plata",
    "bolsillos": "bolsillos_plata",
    "fiducuenta": "fiducuenta_plata",
    "cdt": "cdt_inversion_virtual_plata",
    "inversion_virtual": "cdt_inversion_virtual_plata",
    "invesbot": "invesbot_plata",
}


def _pivotear_producto(clientes_ids, producto):
    tabla = TABLAS_PRODUCTO[producto]
    df = leer_tabla_sqlite(config.PLATA_DB, tabla)
    df = df[df["producto"] == producto].drop(columns=["producto", "fecha_snapshot"])
    df = df.rename(columns={
        "saldo_snapshot": f"{producto}_saldo_snapshot",
        "saldo_prom_6m": f"{producto}_saldo_prom_6m",
        "tendencia_6m": f"{producto}_tendencia_6m",
        "tenencia": f"{producto}_tenencia",
    })
    return df


def construir_cliente_features():
    base = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")

    for producto in PRODUCTOS:
        df_producto = _pivotear_producto(base["numero_id"], producto)
        base = base.merge(df_producto, on="numero_id", how="left")
        base[f"{producto}_saldo_snapshot"] = base[f"{producto}_saldo_snapshot"].fillna(0.0)
        base[f"{producto}_saldo_prom_6m"] = base[f"{producto}_saldo_prom_6m"].fillna(0.0)
        base[f"{producto}_tendencia_6m"] = base[f"{producto}_tendencia_6m"].fillna(0.0)
        base[f"{producto}_tenencia"] = base[f"{producto}_tenencia"].fillna(0).astype(int)

    estimador = leer_tabla_sqlite(config.PLATA_DB, "estimador_ingresos_plata")
    base = base.merge(estimador, on="numero_id", how="left")
    base["tiene_estimador_ingreso"] = base["tiene_estimador_ingreso"].fillna(False).astype(bool)

    base["etiqueta_adopcion"] = (
        (base["invesbot_saldo_snapshot"] > 0) | (base["inversion_virtual_saldo_snapshot"] > 0)
    ).astype(int)

    tenencia_cols = [f"{p}_tenencia" for p in PRODUCTOS]
    base["excluir_modelado"] = (
        (base[tenencia_cols].sum(axis=1) == 0) & (~base["tiene_estimador_ingreso"])
    ).astype(int)

    escribir_tabla_sqlite(base, config.ORO_DB, "cliente_features")
    return base


if __name__ == "__main__":
    df = construir_cliente_features()
    print(f"cliente_features: {len(df)} filas, {df.shape[1]} columnas")
    print(f"tasa adopción: {df['etiqueta_adopcion'].mean():.4f}")
    print(f"excluidos del modelado: {df['excluir_modelado'].sum()}")
