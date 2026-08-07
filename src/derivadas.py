"""Variables derivadas de cliente_features (SPEC_V2 §5) y tratamiento de
`desc_tipo_de_vivienda` como categoría con nivel "Sin dato" (§6.5).

Regla transversal: toda división devuelve NaN cuando el denominador es 0 o nulo.
Un `inf` en una feature envenena cualquier modelo lineal y distorsiona los
percentiles de los modelos de árbol; un NaN es información honesta ("no se puede
calcular") que HistGradientBoosting maneja nativamente.
"""
import numpy as np
import pandas as pd

import config

ETIQUETA_SIN_DATO = "Sin dato"


def division_segura(numerador, denominador, denominador_positivo: bool = False) -> pd.Series:
    """División elemento a elemento; NaN (nunca inf) si el denominador es 0 o nulo.

    `denominador_positivo=True` también anula el resultado cuando el
    denominador es negativo (D3/N2: con un denominador negativo el signo del
    ratio se invierte y deja de significar lo que se quiere medir).
    """
    num = pd.Series(numerador).astype("float64")
    den = pd.Series(denominador).astype("float64")
    if denominador_positivo:
        den = den.mask(den <= 0)      # 0 o negativo -> NaN
    else:
        den = den.mask(den == 0)      # 0 -> NaN, y NaN/NaN = NaN
    return num / den


def agregar_ratios_financieros(df: pd.DataFrame) -> pd.DataFrame:
    """Los 6 ratios de capacidad financiera de SPEC_V2 §5."""
    out = df.copy()
    out["ratio_egreso_ingreso"] = division_segura(
        out["total_egresos_mensuales"], out["ingresos_mensuales"])
    out["pct_ahorro_ingreso"] = division_segura(
        out["capacidad_ahorro"], out["ingresos_mensuales"])
    out["ratio_pasivo_activo"] = division_segura(
        out["total_pasivos"], out["total_activos"])
    out["patrimonio_por_ingreso"] = division_segura(
        out["total_patrimonio"], out["ingresos_mensuales"] * 12)
    # D10: la variable se llama dif_ingreso_declarado_estimado (antes
    # gap_ingreso_estimado_declarado, un nombre que contradecía su propia
    # fórmula). Se conserva la fórmula del spec: declarado − estimado.
    out["dif_ingreso_declarado_estimado"] = (
        out["ingresos_mensuales"] - out["estimador_ingreso"])
    out["pct_dif_ingreso"] = division_segura(
        out["dif_ingreso_declarado_estimado"], out["ingresos_mensuales"])
    return out


def agregar_tendencia_relativa(df: pd.DataFrame) -> pd.DataFrame:
    """`{producto}_tendencia_relativa_6m` para cada producto (D3).

    tendencia_relativa = tendencia_6m / saldo_prom_6m. La tendencia en pesos
    absolutos no es comparable entre clientes de distinta escala patrimonial;
    el ratio sí. `denominador_positivo=True` (N2): con `saldo_prom_6m` <= 0 el
    ratio pierde sentido direccional, así que se descarta a nulo en vez de
    invertir el signo.
    """
    out = df.copy()
    for producto in config.PRODUCTOS:
        col_tend = f"{producto}_tendencia_6m"
        col_prom = f"{producto}_saldo_prom_6m"
        if col_tend not in out.columns or col_prom not in out.columns:
            continue
        out[f"{producto}_tendencia_relativa_6m"] = division_segura(
            out[col_tend], out[col_prom], denominador_positivo=True)
    return out


def agregar_agregados_producto(df: pd.DataFrame) -> pd.DataFrame:
    """Saldo líquido, conteos de producto y ratio de liquidez (SPEC_V2 §5).

    `n_productos_total` incluye Invesbot e Inversión Virtual, así que es
    DESCRIPTIVA, no predictora: está en la lista negra de `src/fuga.py`.
    """
    out = df.copy()
    cols_liquidos = [f"{p}_saldo_snapshot" for p in config.PRODUCTOS_LIQUIDOS]
    cols_todos = [f"{p}_saldo_snapshot" for p in config.PRODUCTOS]
    cols_no_etiqueta = [
        f"{p}_saldo_snapshot" for p in config.PRODUCTOS
        if p not in config.PRODUCTOS_ETIQUETA
    ]

    out["saldo_liquido_total"] = out[cols_liquidos].fillna(0.0).sum(axis=1)
    out["n_productos_total"] = (out[cols_todos].fillna(0.0) > 0).sum(axis=1).astype(int)
    out["n_productos_no_etiqueta"] = (
        (out[cols_no_etiqueta].fillna(0.0) > 0).sum(axis=1).astype(int))
    out["ratio_liquidez_patrimonio"] = division_segura(
        out["saldo_liquido_total"], out["total_patrimonio"])
    return out


def agregar_banderas_faltantes(df: pd.DataFrame, cols_por_bloque: dict) -> pd.DataFrame:
    """Una bandera `falta_<bloque>` por bloque de variables (SPEC_V2 §5).

    Vale 1 si TODAS las columnas del bloque están nulas: la bandera marca
    "el bloque no se capturó", no "falta un campo suelto".
    """
    out = df.copy()
    for bloque, cols in cols_por_bloque.items():
        presentes = [c for c in cols if c in out.columns]
        if not presentes:
            continue
        out[f"falta_{bloque}"] = out[presentes].isnull().all(axis=1).astype(int)
    return out


def agregar_vivienda_como_categoria(df: pd.DataFrame,
                                    etiqueta: str = ETIQUETA_SIN_DATO) -> pd.DataFrame:
    """Missing as a category para `desc_tipo_de_vivienda` (SPEC_V2 §6.5).

    Con ~68% de nulos, imputar fabricaría la mayoría de la columna y el modelo
    aprendería la imputación. El nulo pasa a ser un nivel más.
    """
    out = df.copy()
    col = "desc_tipo_de_vivienda"
    out["tiene_dato_vivienda"] = out[col].notna().astype(int)
    out[col] = out[col].astype(object).where(out[col].notna(), etiqueta)
    return out


def resumen_cv_saldo_liquido(panel_mensual: pd.DataFrame, productos_liquidos=None,
                             *, fecha_corte, meses_ventana: int | None = None,
                             meses_minimos: int | None = None) -> pd.DataFrame:
    """Coeficiente de variación del saldo líquido mensual por cliente (D9).

    D9 CAMBIA la propuesta provisional (desviación absoluta sobre todo el
    historial disponible) en tres puntos:
      1. Ventana FIJA de `meses_ventana` (por defecto `config.VENTANA_MESES_AGREGACION`)
         contada hacia atrás desde `fecha_corte` — no todo el historial. Clientes
         con historias de distinta longitud producían desviaciones no comparables.
      2. Mínimo de `meses_minimos` (por defecto `config.MESES_MINIMOS_CV_LIQUIDO`)
         meses con dato REAL (columna `observado` de `src/panel_mensual.py`, no
         arrastrado por forward fill). Por debajo, nulo con bandera
         `cv_saldo_liquido_insuficiente`, no un valor calculado sobre pocos puntos.
      3. Coeficiente de variación (std poblacional / media) en vez de la
         desviación absoluta, por la misma razón de escala que `tendencia_relativa`
         (D3). Media <= 0 -> nulo (sin bandera: hubo dato suficiente, el problema
         es la escala, no la cantidad de datos).
    """
    if productos_liquidos is None:
        productos_liquidos = config.PRODUCTOS_LIQUIDOS
    meses_ventana = meses_ventana or config.VENTANA_MESES_AGREGACION
    meses_minimos = meses_minimos or config.MESES_MINIMOS_CV_LIQUIDO
    fecha_corte = pd.Timestamp(fecha_corte)
    ventana_ini = fecha_corte - pd.DateOffset(months=meses_ventana)

    liquidos = panel_mensual[
        panel_mensual["producto"].isin(productos_liquidos)
        & (panel_mensual["mes"] >= ventana_ini)
        & (panel_mensual["mes"] <= fecha_corte)
    ]
    if liquidos.empty:
        return pd.DataFrame(columns=[
            "numero_id", "cv_saldo_liquido", "cv_saldo_liquido_insuficiente"])

    por_mes = (
        liquidos.groupby(["numero_id", "mes"], as_index=False)
        .agg(saldo_mes=("saldo_mes", "sum"), observado=("observado", "max"))
    )
    stats = (
        por_mes.groupby("numero_id", as_index=False)
        .agg(media=("saldo_mes", "mean"),
             std=("saldo_mes", lambda s: s.std(ddof=0)),
             n_meses_observados=("observado", "sum"))
    )

    stats["cv_saldo_liquido_insuficiente"] = (
        stats["n_meses_observados"] < meses_minimos).astype(int)
    media_valida = stats["media"] > 0
    stats["cv_saldo_liquido"] = np.where(
        (stats["cv_saldo_liquido_insuficiente"] == 0) & media_valida,
        stats["std"] / stats["media"],
        np.nan,
    )
    return stats[["numero_id", "cv_saldo_liquido", "cv_saldo_liquido_insuficiente"]]
