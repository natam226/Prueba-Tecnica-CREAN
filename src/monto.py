"""Modelo de monto a 12 meses: crecimiento, backtesting y escenarios (SPEC_V2 §6.3).

LIMITACIÓN estructural que el notebook debe documentar: con ~13 meses de historia
no es posible validar un horizonte de 12 meses de forma rigurosa ni capturar
estacionalidad anual. El backtest valida contra 3 meses; los 12 meses son una
extrapolación. El resultado se reporta SIEMPRE como rango, nunca como cifra única.
"""
import numpy as np
import pandas as pd

import config


def crecimiento_anualizado(saldo_inicial, saldo_final, meses) -> pd.Series:
    """Crecimiento ABSOLUTO observado, escalado linealmente a 12 meses.

    Absoluto y no compuesto: con saldos que arrancan en 0 (adquisición en frío)
    una tasa compuesta es indefinida o explota. `meses <= 0` devuelve NaN, nunca inf.
    """
    ini = pd.Series(saldo_inicial).astype("float64")
    fin = pd.Series(saldo_final).astype("float64")
    m = pd.Series(meses).astype("float64").mask(lambda s: s <= 0)
    return (fin - ini) * 12.0 / m


def split_backtesting_temporal(panel: pd.DataFrame, col_mes: str,
                               n_meses_validacion: int | None = None):
    """Split temporal: primeros N−k meses para entrenar, últimos k para validar.

    El split es TEMPORAL, no aleatorio: un split aleatorio dejaría meses futuros
    en el entrenamiento y el backtest no mediría nada.
    """
    k = config.MESES_VALIDACION_BACKTEST if n_meses_validacion is None else n_meses_validacion
    meses = np.sort(pd.Series(panel[col_mes]).unique())
    if len(meses) <= k:
        raise ValueError(
            f"historia insuficiente: {len(meses)} meses disponibles, "
            f"se necesitan más de {k} para dejar {k} de validación"
        )
    corte = meses[-k]
    train = panel[panel[col_mes] < corte]
    valid = panel[panel[col_mes] >= corte]
    return train, valid


def mae_mape(y_real, y_pred, eps: float = 1.0) -> dict:
    """MAE y MAPE (SPEC_V2 §6.3.4).

    El MAPE excluye los casos con |real| <= eps: con saldos que valen 0 el
    porcentaje de error es indefinido y una sola fila lo llevaría a infinito.
    Se reporta `n_mape` para que quede claro sobre cuántos casos se calculó.
    """
    real = np.asarray(y_real, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(real) & np.isfinite(pred)
    if not ok.any():
        return {"mae": float("nan"), "mape": float("nan"), "n": 0, "n_mape": 0}

    real_ok, pred_ok = real[ok], pred[ok]
    mae = float(np.mean(np.abs(real_ok - pred_ok)))

    denom = np.abs(real_ok)
    validos = denom > eps
    mape = (float(np.mean(np.abs((real_ok[validos] - pred_ok[validos]) / denom[validos])))
            if validos.any() else float("nan"))
    return {"mae": mae, "mape": mape, "n": int(ok.sum()), "n_mape": int(validos.sum())}


def escenarios_desde_errores(predicciones, errores, p_bajo: float = 25,
                             p_alto: float = 75) -> pd.DataFrame:
    """Tres escenarios a partir de la distribución empírica del error de backtest.

    Convención de signo: error = real − predicho. El escenario conservador suma
    el percentil bajo del error (típicamente negativo) y el optimista el alto.
    """
    pred = pd.Series(predicciones).astype("float64")
    err = np.asarray(errores, dtype=float)
    err = err[np.isfinite(err)]
    if err.size == 0:
        lo = hi = 0.0
    else:
        lo = float(np.percentile(err, p_bajo))
        hi = float(np.percentile(err, p_alto))

    return pd.DataFrame({
        "conservador": pred + lo,
        "base": pred,
        "optimista": pred + hi,
    }, index=pred.index)
