import numpy as np
import pandas as pd

from src.niveles import asignar_niveles, asignar_niveles_por_poblacion


def test_cuartiles_reparten_en_cuatro_bloques_iguales():
    niveles = asignar_niveles(pd.Series(range(100)))
    assert niveles.value_counts().to_dict() == {"A": 25, "B": 25, "C": 25, "D": 25}
    assert niveles.iloc[99] == "A"     # el valor más alto va al nivel A
    assert niveles.iloc[0] == "D"


def test_muchos_empates_no_rompen_el_corte():
    """Los scores de propensión tienen masas grandes en valores bajos:
    qcut fallaría por bordes duplicados."""
    valores = pd.Series([0.0] * 80 + [0.5] * 10 + [0.9] * 10)
    niveles = asignar_niveles(valores)
    assert niveles.notna().all()
    assert set(niveles) == {"A", "B", "C", "D"}
    assert niveles.iloc[-1] == "A"


def test_nulos_quedan_sin_nivel():
    valores = pd.Series([1.0, 2.0, np.nan, 4.0])
    niveles = asignar_niveles(valores)
    assert pd.isna(niveles.iloc[2])
    assert niveles.iloc[3] == "A"


def test_serie_vacia_o_toda_nula_devuelve_todo_nulo():
    assert asignar_niveles(pd.Series([np.nan, np.nan])).isna().all()
    assert len(asignar_niveles(pd.Series([], dtype=float))) == 0


def test_por_poblacion_los_cuartiles_son_independientes():
    """SPEC_V2 §6.2: A/B/C/D se asignan por separado DENTRO de cada población,
    para no comparar poblaciones no comparables."""
    df = pd.DataFrame({
        "valor": [1, 2, 3, 4, 100, 200, 300, 400],
        "poblacion": ["sin_historial"] * 4 + ["con_historial"] * 4,
    })
    niveles = asignar_niveles_por_poblacion(df, "valor", "poblacion")
    # el 4 es el mejor de su población -> A, aunque sea 100x menor que el peor de la otra
    assert niveles.iloc[3] == "A"
    assert niveles.iloc[4] == "D"      # el 100 es el peor de la suya
    assert niveles.iloc[7] == "A"


def test_por_poblacion_conserva_el_indice_original():
    df = pd.DataFrame({"valor": [3.0, 1.0, 2.0], "poblacion": ["x", "x", "x"]},
                      index=[10, 20, 30])
    niveles = asignar_niveles_por_poblacion(df, "valor", "poblacion")
    assert niveles.index.tolist() == [10, 20, 30]
    assert niveles.loc[10] == "A"
