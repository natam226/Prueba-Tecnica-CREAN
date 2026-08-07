import numpy as np
import pandas as pd
import pytest

from src.feature_tests import (
    benjamini_hochberg,
    binear,
    calcular_vif,
    calcular_woe_iv,
    chi2_y_cramer,
    clasificar_iv,
    mann_whitney,
)

RNG = np.random.default_rng(42)


# --- IV / WoE ---

def test_iv_alto_cuando_la_variable_separa_la_etiqueta():
    y = pd.Series([0] * 500 + [1] * 500)
    x = pd.Series(list(RNG.normal(0, 1, 500)) + list(RNG.normal(6, 1, 500)))
    iv, tabla = calcular_woe_iv(x, y)
    assert iv > 0.3
    assert clasificar_iv(iv) == "fuerte"
    assert set(tabla.columns) >= {"bin", "n", "eventos", "no_eventos", "woe", "iv_bin"}
    assert tabla["n"].sum() == 1000


def test_iv_bajo_cuando_no_hay_relacion():
    y = pd.Series(RNG.integers(0, 2, 4000))
    x = pd.Series(RNG.normal(0, 1, 4000))
    iv, _ = calcular_woe_iv(x, y)
    assert iv < 0.1


def test_iv_trata_los_nulos_como_un_bin_mas():
    """SPEC_V2 §4: para desc_tipo_de_vivienda, "Sin dato" es un bin más."""
    x = pd.Series(["PROPIA"] * 100 + ["ARRENDADA"] * 100 + [None] * 200)
    y = pd.Series([1] * 50 + [0] * 50 + [1] * 20 + [0] * 80 + [0] * 200)
    iv, tabla = calcular_woe_iv(x, y)
    assert "Sin dato" in tabla["bin"].astype(str).tolist()
    assert tabla["n"].sum() == 400


@pytest.mark.parametrize("iv,esperado", [
    (0.001, "descartar"), (0.019, "descartar"), (0.02, "debil"),
    (0.09, "debil"), (0.1, "media"), (0.29, "media"), (0.3, "fuerte"), (1.2, "fuerte"),
])
def test_clasificar_iv_usa_los_cortes_del_spec(iv, esperado):
    assert clasificar_iv(iv) == esperado


def test_binear_no_falla_con_muchos_empates():
    """Los saldos tienen enormes masas en 0: qcut duplicaría bordes."""
    x = pd.Series([0.0] * 900 + list(range(100)))
    b = binear(x, n_bins=10)
    assert b.notna().all()
    assert b.nunique() >= 2


# --- Mann-Whitney ---

def test_mann_whitney_detecta_diferencia_de_distribucion():
    y = pd.Series([0] * 300 + [1] * 300)
    x = pd.Series(list(RNG.normal(0, 1, 300)) + list(RNG.normal(3, 1, 300)))
    r = mann_whitney(x, y)
    assert r["p_valor"] < 0.001
    assert r["mediana_evento"] > r["mediana_no_evento"]


def test_mann_whitney_ignora_nulos():
    y = pd.Series([0, 0, 1, 1])
    x = pd.Series([1.0, np.nan, 5.0, 6.0])
    r = mann_whitney(x, y)
    assert not np.isnan(r["p_valor"])


def test_mann_whitney_sin_un_grupo_devuelve_nan():
    r = mann_whitney(pd.Series([1.0, 2.0]), pd.Series([0, 0]))
    assert np.isnan(r["p_valor"])


# --- Chi-cuadrado y V de Cramér ---

def test_cramer_cercano_a_uno_con_asociacion_perfecta():
    x = pd.Series(["a"] * 200 + ["b"] * 200)
    y = pd.Series([1] * 200 + [0] * 200)
    r = chi2_y_cramer(x, y)
    assert r["v_cramer"] > 0.95
    assert r["p_valor"] < 1e-10


def test_cramer_cercano_a_cero_con_independencia():
    x = pd.Series(RNG.choice(["a", "b", "c"], 5000))
    y = pd.Series(RNG.integers(0, 2, 5000))
    assert chi2_y_cramer(x, y)["v_cramer"] < 0.1


def test_cramer_trata_nulos_como_categoria():
    x = pd.Series(["a", None, "b", None])
    y = pd.Series([1, 0, 1, 0])
    r = chi2_y_cramer(x, y)
    assert not np.isnan(r["chi2"])


# --- Benjamini-Hochberg ---

def test_benjamini_hochberg_ejemplo_clasico():
    q, rechaza = benjamini_hochberg([0.001, 0.008, 0.039, 0.041, 0.042], alpha=0.05)
    assert rechaza.tolist() == [True, True, True, True, True]
    assert q[0] == pytest.approx(0.005)


def test_benjamini_hochberg_es_mas_estricto_que_alpha_crudo():
    # NOTA: la lista original del brief era `[0.001] + [0.04] * 20` (m=21).
    # Con el procedimiento step-up de BH, el p-valor de mayor rango se compara
    # contra (m/m)*alpha = alpha exactamente, así que 0.04 <= 0.05 en la
    # última posición dispara el rechazo de TODAS las hipótesis (propiedad
    # real y documentada del método, no un bug de la implementación). Ese
    # caso no demuestra "más estricto que alpha crudo": demuestra lo
    # contrario. Se añaden 20 p-valores claramente nulos (0.9) para que el
    # bloque marginal de 0.04 dejen de estar en el rango más alto y el
    # ejemplo sí ilustre la corrección FDR.
    p = [0.001] + [0.04] * 20 + [0.9] * 20
    q, rechaza = benjamini_hochberg(p, alpha=0.05)
    assert rechaza[0]
    assert not rechaza[1:21].any()   # 0.04 < 0.05 pero no sobrevive la corrección FDR


def test_benjamini_hochberg_q_no_decrece_con_p():
    p = np.array([0.01, 0.02, 0.03, 0.5])
    q, _ = benjamini_hochberg(p)
    assert np.all(np.diff(q) >= -1e-12)


def test_benjamini_hochberg_rechaza_nan():
    with pytest.raises(ValueError):
        benjamini_hochberg([0.01, np.nan])


# --- VIF ---

def test_vif_dispara_con_dependencia_contable():
    """SPEC_V2 §4.5: patrimonio = activos − pasivos por definición contable."""
    activos = RNG.normal(10_000, 2_000, 500)
    pasivos = RNG.normal(3_000, 800, 500)
    df = pd.DataFrame({
        "total_activos": activos,
        "total_pasivos": pasivos,
        "total_patrimonio": activos - pasivos,
    })
    r = calcular_vif(df).set_index("variable")
    assert r.loc["total_patrimonio", "vif"] > 10


def test_vif_cercano_a_uno_con_variables_independientes():
    df = pd.DataFrame({
        "a": RNG.normal(0, 1, 1000),
        "b": RNG.normal(0, 1, 1000),
        "c": RNG.normal(0, 1, 1000),
    })
    r = calcular_vif(df)
    assert (r["vif"] < 1.5).all()
