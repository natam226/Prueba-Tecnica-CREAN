"""Ubicación de un valor en los tramos de WoE y lectura de su signo."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.explicacion import (
    SIN_DATO, clasificar_direccion, evidencia_del_cliente, ubicar_bin,
)

# Las tres formas que produce el binning, tal como aparecen en el artefacto real.
INTERVALOS = ["(-0.001, 4.0]", "(4.0, 6.0]", "(6.0, 9.0]", SIN_DATO]
LITERALES = ["0", "1", "2"]
IGUALDADES = ["= 0.0", "= 1.0"]


@pytest.mark.parametrize("valor, esperado", [
    (0.0, "(-0.001, 4.0]"),
    (4.0, "(-0.001, 4.0]"),   # cerrado por la derecha
    (4.5, "(4.0, 6.0]"),
    (6.0, "(4.0, 6.0]"),
    (9.0, "(6.0, 9.0]"),
])
def test_intervalos_respetan_los_extremos(valor, esperado):
    assert ubicar_bin(valor, INTERVALOS) == esperado


def test_valor_fuera_de_todo_tramo_devuelve_none():
    """Deriva: el binning ya no cubre este valor. Mejor None que inventar."""
    assert ubicar_bin(99.0, INTERVALOS) is None
    assert ubicar_bin(-5.0, INTERVALOS) is None


@pytest.mark.parametrize("nulo", [None, np.nan, pd.NA])
def test_nulo_cae_en_sin_dato(nulo):
    assert ubicar_bin(nulo, INTERVALOS) == SIN_DATO


def test_nulo_sin_tramo_de_sin_dato_devuelve_none():
    assert ubicar_bin(None, ["(0.0, 1.0]"]) is None


def test_literales_y_igualdades():
    assert ubicar_bin(1, LITERALES) == "1"
    assert ubicar_bin(1.0, LITERALES) == "1"        # 1.0 y "1" son el mismo bin
    assert ubicar_bin(0.0, IGUALDADES) == "= 0.0"
    assert ubicar_bin(7, LITERALES) is None


def test_categorias_de_texto():
    assert ubicar_bin("PROPIA", ["PROPIA", "ARRENDADA"]) == "PROPIA"
    assert ubicar_bin("OTRA", ["PROPIA", "ARRENDADA"]) is None


@pytest.mark.parametrize("woe, esperado", [
    (1.5, "en contra"),    # positivo = sobre-representado entre NO adoptantes
    (-1.5, "a favor"),
    (0.01, "neutro"),
    (float("nan"), "neutro"),
])
def test_el_signo_se_traduce_a_texto(woe, esperado):
    """El WoE de este proyecto es ln(%no_eventos/%eventos): positivo = en contra.

    Es el inverso de la convención más difundida, así que el número nunca se
    muestra solo y esta traducción es la que evita leerlo al revés.
    """
    assert clasificar_direccion(woe) == esperado


def _woe_de_prueba():
    return pd.DataFrame([
        {"variable": "edad_meses", "bin": "(-0.001, 4.0]", "woe": 0.96, "n": 100},
        {"variable": "edad_meses", "bin": "(4.0, 6.0]", "woe": -0.46, "n": 200},
        {"variable": "tenencia", "bin": "0", "woe": 1.09, "n": 300},
        {"variable": "tenencia", "bin": "1", "woe": -2.10, "n": 400},
        {"variable": "no_esta_en_el_cliente", "bin": "0", "woe": 0.5, "n": 10},
    ])


def test_evidencia_ordena_por_fuerza_y_omite_lo_que_no_resuelve():
    features = pd.Series({"edad_meses": 5.0, "tenencia": 1, "otra_cosa": 3})
    ev = evidencia_del_cliente(features, _woe_de_prueba())

    # `no_esta_en_el_cliente` no está en features y no debe aparecer.
    assert list(ev["variable"]) == ["tenencia", "edad_meses"]
    assert ev.iloc[0]["woe"] == pytest.approx(-2.10)
    assert ev.iloc[0]["direccion"] == "a favor"
    assert ev.iloc[1]["bin"] == "(4.0, 6.0]"
    assert (ev["fuerza"].diff().dropna() <= 0).all(), "debe ir de mayor a menor"


def test_evidencia_sin_coincidencias_devuelve_tabla_vacia_con_columnas():
    features = pd.Series({"edad_meses": 999.0})
    ev = evidencia_del_cliente(features, _woe_de_prueba())
    assert ev.empty
    assert "direccion" in ev.columns
