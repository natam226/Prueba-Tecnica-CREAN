import numpy as np
import pandas as pd
import pytest

from src.monto import (
    crecimiento_anualizado,
    escenarios_desde_errores,
    mae_mape,
    split_backtesting_temporal,
)


def test_crecimiento_anualizado_escala_a_doce_meses():
    # +600 en 6 meses -> +1200 anualizado
    r = crecimiento_anualizado(pd.Series([1000.0]), pd.Series([1600.0]), pd.Series([6]))
    assert r.iloc[0] == pytest.approx(1200.0)


def test_crecimiento_anualizado_admite_decrecimiento():
    r = crecimiento_anualizado(pd.Series([1000.0]), pd.Series([700.0]), pd.Series([6]))
    assert r.iloc[0] == pytest.approx(-600.0)


def test_crecimiento_anualizado_con_cero_meses_es_nulo_no_infinito():
    r = crecimiento_anualizado(pd.Series([100.0]), pd.Series([200.0]), pd.Series([0]))
    assert pd.isna(r.iloc[0])
    assert not np.isinf(r.to_numpy(dtype=float, na_value=0.0)).any()


def test_split_temporal_deja_los_ultimos_n_meses_para_validacion():
    """SPEC_V2 §6.3.4: entrenar con los primeros N−3 meses, validar contra los últimos 3."""
    panel = pd.DataFrame({
        "numero_id": [1] * 12,
        "mes": pd.date_range("2025-07-01", periods=12, freq="MS"),
        "saldo_mes": range(12),
    })
    train, valid = split_backtesting_temporal(panel, "mes", n_meses_validacion=3)
    assert train["mes"].max() < valid["mes"].min()
    assert valid["mes"].nunique() == 3
    assert train["mes"].nunique() == 9
    assert len(train) + len(valid) == len(panel)


def test_split_temporal_lanza_si_no_hay_historia_suficiente():
    panel = pd.DataFrame({
        "numero_id": [1, 1],
        "mes": pd.to_datetime(["2026-01-01", "2026-02-01"]),
        "saldo_mes": [1.0, 2.0],
    })
    with pytest.raises(ValueError):
        split_backtesting_temporal(panel, "mes", n_meses_validacion=3)


def test_mae_mape():
    r = mae_mape([100.0, 200.0], [110.0, 180.0])
    assert r["mae"] == pytest.approx(15.0)
    assert r["mape"] == pytest.approx((0.10 + 0.10) / 2)
    assert r["n"] == 2


def test_mape_excluye_denominadores_cercanos_a_cero():
    r = mae_mape([0.0, 100.0], [50.0, 110.0], eps=1.0)
    assert r["n"] == 2
    assert r["n_mape"] == 1          # el real 0.0 no entra al MAPE
    assert r["mape"] == pytest.approx(0.10)


def test_mae_mape_ignora_nan():
    r = mae_mape([100.0, np.nan], [110.0, 5.0])
    assert r["n"] == 1
    assert r["mae"] == pytest.approx(10.0)


def test_mae_mape_incluye_mediana_ape_robusta_a_cola():
    """Amendment SPEC_V2 §6.3.4 (DECISIONES.md clave=metrica_error_monto): la
    MEDIA del APE la domina un solo ratio extremo (real casi 0); la MEDIANA no."""
    # reales = [100, 100, 100, 100, 1.0] -> el ultimo real casi-cero con un
    # error grande dispara la media pero no la mediana.
    reales = [100.0, 100.0, 100.0, 100.0, 1.0]
    preds = [110.0, 110.0, 110.0, 110.0, 500.0]   # ratios: .10,.10,.10,.10, 499.0
    r = mae_mape(reales, preds, eps=0.5)
    assert r["n_mape"] == 5
    assert r["mape_mediana"] == pytest.approx(0.10)
    assert r["mape"] > 50.0          # la media SI se dispara por la cola


def test_escenarios_ordenan_conservador_base_optimista():
    """SPEC_V2 §6.3.5: conservador = p25 del error, base = predicción recentrada
    por la mediana del error, optimista = p75."""
    errores = np.array([-50.0, -20.0, 0.0, 20.0, 50.0])   # p25=-20, mediana=0, p75=20
    r = escenarios_desde_errores(pd.Series([1000.0, 2000.0]), errores)
    assert r.loc[0, "base"] == 1000.0
    assert r.loc[0, "conservador"] == pytest.approx(980.0)
    assert r.loc[0, "optimista"] == pytest.approx(1020.0)
    assert (r["conservador"] <= r["base"]).all()
    assert (r["base"] <= r["optimista"]).all()


def test_escenarios_conservan_el_indice():
    r = escenarios_desde_errores(pd.Series([10.0], index=[7]), np.array([-1.0, 1.0]))
    assert r.index.tolist() == [7]


def test_escenarios_recentran_base_cuando_hay_sesgo_sistematico():
    """Diagnostico monto_12m: el modelo sobre-predice de forma sistematica
    (mediana del error negativa) -- 'base' debe recentrarse por esa mediana,
    no quedarse en la prediccion cruda, o arrastraria el sesgo al negocio."""
    errores = np.array([-100.0, -90.0, -80.0, -10.0, -5.0])   # todo negativo
    r = escenarios_desde_errores(pd.Series([1000.0]), errores, p_bajo=10, p_alto=90)
    mediana_error = -80.0
    assert r.loc[0, "base"] == pytest.approx(1000.0 + mediana_error)
    assert r.loc[0, "base"] < 1000.0    # ya no es la prediccion cruda sin corregir
    assert r.loc[0, "conservador"] <= r.loc[0, "base"] <= r.loc[0, "optimista"]


def test_escenarios_orden_garantizado_incluso_con_banda_de_ancho_cero():
    """Reproduce el caso 'app' de monto_12m: 78%+ de los errores son el MISMO
    valor negativo (masa de empates), colapsando p10==p50==p90. El orden
    conservador <= base <= optimista debe seguir cumpliendose (con igualdad),
    no romperse -- es la garantia por construccion que motivo el fix."""
    errores = np.array([-65253.23] * 8 + [-10.0, 5.0])
    r = escenarios_desde_errores(pd.Series([1_000_000.0]), errores, p_bajo=10, p_alto=90)
    assert r.loc[0, "conservador"] <= r.loc[0, "base"] <= r.loc[0, "optimista"]
    # banda degenerada: p10 == mediana en este caso concreto
    assert r.loc[0, "conservador"] == pytest.approx(r.loc[0, "base"])


def test_escenarios_p10_p90_ensancha_banda_respecto_a_p25_p75():
    errores = np.random.RandomState(0).normal(loc=-1000.0, scale=500.0, size=1000)
    estrecha = escenarios_desde_errores(pd.Series([0.0]), errores, p_bajo=25, p_alto=75)
    ancha = escenarios_desde_errores(pd.Series([0.0]), errores, p_bajo=10, p_alto=90)
    ancho_estrecho = estrecha.loc[0, "optimista"] - estrecha.loc[0, "conservador"]
    ancho_ancho = ancha.loc[0, "optimista"] - ancha.loc[0, "conservador"]
    assert ancho_ancho > ancho_estrecho
    # ambas bandas deben quedar correctamente ordenadas y centradas en la misma mediana
    assert estrecha.loc[0, "base"] == pytest.approx(ancha.loc[0, "base"])
