import pandas as pd


def agregar_serie_saldo(df, group_cols, fecha_corte, fecha_col="fecha", saldo_col="saldo", meses_ventana=6):
    """Snapshot / promedio 6M / tendencia 6M contra una fecha de corte GLOBAL (D4).

    `fecha_corte` ya no se infiere de `df[fecha_col].max()` (eso mediría cada
    fuente, o peor, cada grupo, en un momento distinto). Se recibe siempre como
    parámetro externo — típicamente `src.fecha_corte.calcular_fecha_corte()` —
    para que TODA la base quede medida contra la misma referencia temporal.
    """
    df = df.copy()
    df[fecha_col] = pd.to_datetime(df[fecha_col])
    fecha_corte = pd.Timestamp(fecha_corte)
    df = df[df[fecha_col] <= fecha_corte]   # D4: se descarta lo posterior al corte
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
    n_obs = (
        ventana.groupby(group_cols, as_index=False)[saldo_col]
        .count()
        .rename(columns={saldo_col: "n_obs_ventana"})
    )

    primera_mitad = ventana[ventana[fecha_col] < mitad].groupby(group_cols)[saldo_col].mean()
    segunda_mitad = ventana[ventana[fecha_col] >= mitad].groupby(group_cols)[saldo_col].mean()
    tendencia = (segunda_mitad - primera_mitad).rename("tendencia_6m").reset_index()

    out = (
        snapshot.merge(prom6m, on=group_cols, how="left")
        .merge(tendencia, on=group_cols, how="left")
        .merge(n_obs, on=group_cols, how="left")
    )
    # Sin datos en la ventana de 6M => dejar NaN real (no se puede calcular), no confundir
    # "sin observación" con "confirmado plano/cero". n_obs_ventana es el único campo que sí
    # es seguro rellenar con 0, porque un conteo de 0 es un hecho, no una suposición.
    out["n_obs_ventana"] = out["n_obs_ventana"].fillna(0).astype(int)
    out["tenencia"] = 1
    return out


def normalizar_producto_inv_virtual(valor: str) -> str:
    if valor == "CDT":
        return "CDT"
    if str(valor).startswith("INVERSI"):
        return "INVERSION_VIRTUAL"
    return valor
