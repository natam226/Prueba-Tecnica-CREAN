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


def test_escenarios_ordenan_conservador_base_optimista():
    """SPEC_V2 §6.3.5: conservador = p25 del error, base = predicción, optimista = p75."""
    errores = np.array([-50.0, -20.0, 0.0, 20.0, 50.0])   # p25=-20, p75=20
    r = escenarios_desde_errores(pd.Series([1000.0, 2000.0]), errores)
    assert r.loc[0, "base"] == 1000.0
    assert r.loc[0, "conservador"] == pytest.approx(980.0)
    assert r.loc[0, "optimista"] == pytest.approx(1020.0)
    assert (r["conservador"] <= r["base"]).all()
    assert (r["base"] <= r["optimista"]).all()


def test_escenarios_conservan_el_indice():
    r = escenarios_desde_errores(pd.Series([10.0], index=[7]), np.array([-1.0, 1.0]))
    assert r.index.tolist() == [7]
