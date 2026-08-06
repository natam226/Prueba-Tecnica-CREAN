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
        "n_obs_ventana": f"{producto}_n_obs_ventana",
    })
    return df


def construir_cliente_features():
    base = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")

    for producto in PRODUCTOS:
        df_producto = _pivotear_producto(base["numero_id"], producto)
        base = base.merge(df_producto, on="numero_id", how="left")

        # sin_producto = cliente sin NINGÚN registro para este producto (ausencia real).
        # Debe capturarse ANTES de rellenar tenencia: agregar_serie_saldo siempre pone
        # tenencia=1 cuando el grupo plata existe, aunque su ventana de 6M esté vacía,
        # así que tenencia NaN post-merge es la señal inequívoca de ausencia total.
        sin_producto = base[f"{producto}_tenencia"].isna()

        base[f"{producto}_tenencia"] = base[f"{producto}_tenencia"].fillna(0).astype(int)
        # saldo_snapshot solo es NaN por ausencia real del producto -> fillna(0.0) incondicional
        base[f"{producto}_saldo_snapshot"] = base[f"{producto}_saldo_snapshot"].fillna(0.0)

        # saldo_prom_6m / tendencia_6m: rellenar con 0.0 SOLO para ausencia real del producto.
        # Si el cliente tiene el producto pero su ventana de 6M no tuvo observaciones, el NaN
        # (heredado de agregar_serie_saldo) debe permanecer: "sin dato" != "confirmado cero".
        base.loc[sin_producto, f"{producto}_saldo_prom_6m"] = (
            base.loc[sin_producto, f"{producto}_saldo_prom_6m"].fillna(0.0)
        )
        base.loc[sin_producto, f"{producto}_tendencia_6m"] = (
            base.loc[sin_producto, f"{producto}_tendencia_6m"].fillna(0.0)
        )
        # n_obs_ventana: un conteo de 0 es un hecho, siempre seguro de rellenar
        base[f"{producto}_n_obs_ventana"] = base[f"{producto}_n_obs_ventana"].fillna(0).astype(int)

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
