"""Regularización de series de saldo a frecuencia mensual (SPEC_V2 §6.3.1).

Un saldo persiste hasta el siguiente movimiento: se rellena hacia adelante
(forward fill), NUNCA se interpola linealmente. Interpolar inventaría
movimientos intermedios que no ocurrieron.

La aritmética de meses se hace sobre un índice entero (`anio * 12 + mes - 1`)
en vez de con Periods, porque la construcción de la rejilla necesita repetir
filas y sumar offsets de forma vectorizada sobre 10⁶-10⁷ filas.
"""
import pandas as pd


def _a_indice_mes(fechas: pd.Series) -> pd.Series:
    return fechas.dt.year * 12 + (fechas.dt.month - 1)


def _a_timestamp_mes(indice: pd.Series) -> pd.Series:
    return pd.to_datetime({
        "year": indice // 12,
        "month": indice % 12 + 1,
        "day": 1,
    })


def primer_mes_por_grupo(df, group_cols, fecha_col="fecha"):
    """Primer mes con registro para cada grupo, como Timestamp de día 1."""
    d = df[list(group_cols) + [fecha_col]].copy()
    d[fecha_col] = pd.to_datetime(d[fecha_col])
    r = d.groupby(list(group_cols), as_index=False)[fecha_col].min()
    r["primer_mes"] = _a_timestamp_mes(_a_indice_mes(r[fecha_col]))
    return r.drop(columns=[fecha_col])


def construir_panel_mensual(df, group_cols, fecha_col="fecha", saldo_col="saldo",
                            mes_max=None):
    """Panel cliente-producto-mes con forward fill.

    Para cada grupo: se toma el ÚLTIMO saldo observado dentro de cada mes, se
    completa la rejilla desde el primer mes del grupo hasta `mes_max` (por
    defecto, el mes máximo observado en `df`), y se rellena hacia adelante.
    """
    group_cols = list(group_cols)
    d = df[group_cols + [fecha_col, saldo_col]].copy()
    d[fecha_col] = pd.to_datetime(d[fecha_col])
    d["idx_mes"] = _a_indice_mes(d[fecha_col])

    # Último saldo observado dentro de cada mes: este mes SÍ tuvo una fila real.
    mensual = (
        d.sort_values(fecha_col)
        .groupby(group_cols + ["idx_mes"], as_index=False)[saldo_col]
        .last()
        .rename(columns={saldo_col: "saldo_mes"})
    )
    mensual["observado"] = 1

    idx_max = (
        int(_a_indice_mes(pd.Series([pd.Timestamp(mes_max)])).iloc[0])
        if mes_max is not None
        else int(mensual["idx_mes"].max())
    )

    # Rejilla completa: de idx_ini(grupo) a idx_max, un mes por fila
    inicio = mensual.groupby(group_cols, as_index=False)["idx_mes"].min()
    inicio = inicio.rename(columns={"idx_mes": "idx_ini"})
    inicio["n_meses"] = idx_max - inicio["idx_ini"] + 1
    inicio = inicio[inicio["n_meses"] > 0]

    rejilla = inicio.loc[inicio.index.repeat(inicio["n_meses"])].copy()
    rejilla["idx_mes"] = (
        rejilla["idx_ini"] + rejilla.groupby(group_cols).cumcount()
    )
    rejilla = rejilla.drop(columns=["idx_ini", "n_meses"])

    panel = (
        rejilla.merge(mensual, on=group_cols + ["idx_mes"], how="left")
        .sort_values(group_cols + ["idx_mes"])
        .reset_index(drop=True)
    )
    # D9 (N5): marcar ANTES del ffill. Un mes sin fila real llega aquí con
    # observado=NaN; tras fillna(0) queda 0, distinguible de los meses reales (1).
    panel["observado"] = panel["observado"].fillna(0).astype(int)
    panel["saldo_mes"] = panel.groupby(group_cols)["saldo_mes"].ffill()
    panel["mes"] = _a_timestamp_mes(panel["idx_mes"])
    return panel[group_cols + ["mes", "saldo_mes", "observado"]]
