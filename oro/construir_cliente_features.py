# oro/construir_cliente_features.py
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite
from src.fecha_corte import calcular_fecha_corte

PRODUCTOS = config.PRODUCTOS

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
    df["fecha_snapshot"] = pd.to_datetime(df["fecha_snapshot"])
    df = df[df["producto"] == producto].drop(columns=["producto"])
    df = df.rename(columns={
        "saldo_snapshot": f"{producto}_saldo_snapshot",
        "saldo_prom_6m": f"{producto}_saldo_prom_6m",
        "tendencia_6m": f"{producto}_tendencia_6m",
        "tenencia": f"{producto}_tenencia",
        "n_obs_ventana": f"{producto}_n_obs_ventana",
        "fecha_snapshot": f"{producto}_fecha_snapshot",   # D0: ya no se descarta
    })
    return df


def agregar_recencia_dato(base: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    """D0, requisito 1: control de calidad de dato por cliente (N1).

    `dias_desde_ultimo_dato` = FECHA_CORTE - máxima fecha_snapshot entre las 5
    fuentes de saldo. Un cliente sin NINGUNA fila de producto queda en NULO +
    bandera `sin_dato_reciente`, nunca en 0 ni en un valor grande arbitrario.
    """
    out = base.copy()
    fecha_cols = [f"{p}_fecha_snapshot" for p in PRODUCTOS]
    presentes = [c for c in fecha_cols if c in out.columns]
    ultimo_dato = out[presentes].max(axis=1)
    out["dias_desde_ultimo_dato"] = (fecha_corte - ultimo_dato).dt.days.astype("Int64")
    out["sin_dato_reciente"] = ultimo_dato.isna().astype(int)
    return out


def agregar_etiqueta_adopcion_reciente(base: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    """D0, análisis de sensibilidad: etiqueta alternativa que SÍ exige recencia
    (N4: ventana de `config.VENTANA_DIAS_ETIQUETA_RECIENTE` días desde
    FECHA_CORTE). Solo se usa para comparar contra la etiqueta principal en la
    Task 18B - la etiqueta principal (`etiqueta_adopcion`) no cambia."""
    out = base.copy()
    ventana = config.VENTANA_DIAS_ETIQUETA_RECIENTE
    reciente_invesbot = (
        (out["invesbot_saldo_snapshot"] > 0)
        & ((fecha_corte - out["invesbot_fecha_snapshot"]).dt.days <= ventana)
    ).fillna(False)
    reciente_iv = (
        (out["inversion_virtual_saldo_snapshot"] > 0)
        & ((fecha_corte - out["inversion_virtual_fecha_snapshot"]).dt.days <= ventana)
    ).fillna(False)
    out["etiqueta_adopcion_reciente"] = (reciente_invesbot | reciente_iv).astype(int)
    return out


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

    fecha_corte = calcular_fecha_corte()
    base = agregar_recencia_dato(base, fecha_corte)
    base = agregar_etiqueta_adopcion_reciente(base, fecha_corte)

    # --- SPEC_V2 §1.1: agregados de inversión que NO tocan la etiqueta ---
    # Solo CDT y Fiducuenta. Nunca Invesbot ni Inversión Virtual: sumarlos
    # reintroduciría la etiqueta dentro de las predictoras.
    cols_saldo_no_etiqueta = [
        f"{p}_saldo_snapshot" for p in config.PRODUCTOS_INVERSION_NO_ETIQUETA
    ]
    base["saldo_invertido_no_etiqueta"] = base[cols_saldo_no_etiqueta].fillna(0.0).sum(axis=1)
    base["n_productos_inversion_no_etiqueta"] = (
        (base[cols_saldo_no_etiqueta].fillna(0.0) > 0).sum(axis=1).astype(int)
    )

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
