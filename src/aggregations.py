import pandas as pd


def agregar_serie_saldo(df, group_cols, fecha_col="fecha", saldo_col="saldo", meses_ventana=6):
    df = df.copy()
    df[fecha_col] = pd.to_datetime(df[fecha_col])
    fecha_corte = df[fecha_col].max()
    ventana_ini = fecha_corte - pd.DateOffset(months=meses_ventana)
    mitad = fecha_corte - pd.DateOffset(months=meses_ventana // 2)

    snapshot = (
        df.sort_values(fecha_col)
        .groupby(group_cols, as_index=False)
        .agg(saldo_snapshot=(saldo_col, "last"), fecha_snapshot=(fecha_col, "last"))
    )

    ventana = df[df[fecha_col] >= ventana_ini]
    prom6m = (
        ventana.groupby(group_cols, as_index=False)[saldo_col]
        .mean()
        .rename(columns={saldo_col: "saldo_prom_6m"})
    )

    primera_mitad = ventana[ventana[fecha_col] < mitad].groupby(group_cols)[saldo_col].mean()
    segunda_mitad = ventana[ventana[fecha_col] >= mitad].groupby(group_cols)[saldo_col].mean()
    tendencia = (segunda_mitad - primera_mitad).rename("tendencia_6m").reset_index()

    out = snapshot.merge(prom6m, on=group_cols, how="left").merge(tendencia, on=group_cols, how="left")
    out["tendencia_6m"] = out["tendencia_6m"].fillna(0.0)
    out["tenencia"] = 1
    return out


def normalizar_producto_inv_virtual(valor: str) -> str:
    if valor == "CDT":
        return "CDT"
    if str(valor).startswith("INVERSI"):
        return "INVERSION_VIRTUAL"
    return valor
