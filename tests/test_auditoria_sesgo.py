import numpy as np
import pandas as pd
import pytest

from src.auditoria_sesgo import (
    cumple_regla_80,
    diferencia_score_por_grupo,
    razon_impacto_dispar,
    tasa_seleccion_por_grupo,
)


def test_tasa_seleccion_por_grupo():
    df = pd.DataFrame({
        "desc_genero": ["M"] * 10 + ["F"] * 10,
        "nivel": ["A"] * 5 + ["B"] * 5 + ["A"] * 2 + ["C"] * 8,
    })
    r = tasa_seleccion_por_grupo(df, "desc_genero", "nivel").set_index("grupo")
    assert r.loc["M", "tasa_seleccion"] == 0.5
    assert r.loc["F", "tasa_seleccion"] == 0.2
    assert r.loc["M", "n"] == 10
    assert r.loc["M", "n_seleccionados"] == 5


def test_tasa_seleccion_incluye_grupos_sin_seleccionados():
    df = pd.DataFrame({"g": ["x", "y"], "nivel": ["A", "D"]})
    r = tasa_seleccion_por_grupo(df, "g", "nivel").set_index("grupo")
    assert r.loc["y", "tasa_seleccion"] == 0.0


def test_tasa_seleccion_trata_nulos_como_grupo():
    df = pd.DataFrame({"g": ["x", None], "nivel": ["A", "A"]})
    r = tasa_seleccion_por_grupo(df, "g", "nivel")
    assert len(r) == 2


def test_razon_impacto_dispar_es_min_sobre_max():
    assert razon_impacto_dispar({"M": 0.10, "F": 0.075}) == pytest.approx(0.75)
    assert razon_impacto_dispar({"M": 0.10, "F": 0.10}) == pytest.approx(1.0)


def test_razon_con_maximo_cero_es_nan():
    assert np.isnan(razon_impacto_dispar({"a": 0.0, "b": 0.0}))


def test_regla_80():
    """SPEC_V2 §6.6.2: por debajo de 0.8 se reporta explícitamente como hallazgo."""
    assert cumple_regla_80(0.81) is True
    assert cumple_regla_80(0.80) is True
    assert cumple_regla_80(0.79) is False


def test_diferencia_score_por_grupo_detecta_brecha():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "g": ["a"] * 500 + ["b"] * 500,
        "score": np.concatenate([rng.normal(0.30, 0.05, 500),
                                 rng.normal(0.10, 0.05, 500)]),
    })
    r = diferencia_score_por_grupo(df, "g", "score").set_index("grupo")
    assert r.loc["a", "score_medio"] > r.loc["b", "score_medio"]
    assert r.loc["a", "p_valor_vs_resto"] < 0.001


def test_diferencia_score_grupo_unico_devuelve_nan():
    df = pd.DataFrame({"g": ["a", "a"], "score": [0.1, 0.2]})
    r = diferencia_score_por_grupo(df, "g", "score")
    assert np.isnan(r.loc[0, "p_valor_vs_resto"])
