"""Auditoría de sesgo del modelo (SPEC_V2 §6.6).

Se ejecuta con independencia de qué variables entren al modelo: excluir una
variable de la lista de entrada no la excluye del modelo si otras la codifican.
"""
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

ETIQUETA_NULOS = "Sin dato"


def tasa_seleccion_por_grupo(df: pd.DataFrame, col_grupo: str, col_nivel: str,
                             nivel_objetivo: str = "A") -> pd.DataFrame:
    """Proporción de cada grupo que llega al nivel objetivo (SPEC_V2 §6.6.2)."""
    g = pd.Series(df[col_grupo]).astype(object)
    g = g.where(g.notna(), ETIQUETA_NULOS)
    sel = (df[col_nivel] == nivel_objetivo).astype(int)

    r = (
        pd.DataFrame({"grupo": g, "sel": sel})
        .groupby("grupo", as_index=False)["sel"]
        .agg(n="count", n_seleccionados="sum")
    )
    r["tasa_seleccion"] = r["n_seleccionados"] / r["n"]
    return r


def razon_impacto_dispar(tasas) -> float:
    """Razón entre el grupo menos y el más favorecido (regla del 80%)."""
    s = pd.Series(tasas, dtype="float64").dropna()
    if s.empty or s.max() == 0:
        return float("nan")
    return float(s.min() / s.max())


def cumple_regla_80(razon: float, umbral: float = 0.8) -> bool:
    """False => hallazgo a reportar explícitamente (SPEC_V2 §6.6.2)."""
    if razon is None or (isinstance(razon, float) and np.isnan(razon)):
        return False
    return bool(razon >= umbral)


def diferencia_score_por_grupo(df: pd.DataFrame, col_grupo: str,
                               col_score: str) -> pd.DataFrame:
    """Score medio por grupo y significancia frente al resto (SPEC_V2 §6.6.3).

    Mann-Whitney y no t-test: la distribución de scores es fuertemente asimétrica.
    """
    g = pd.Series(df[col_grupo]).astype(object)
    g = g.where(g.notna(), ETIQUETA_NULOS)
    score = pd.Series(df[col_score]).astype("float64")

    filas = []
    for grupo in sorted(g.dropna().unique(), key=str):
        dentro = score[(g == grupo) & score.notna()]
        fuera = score[(g != grupo) & score.notna()]
        if len(dentro) == 0 or len(fuera) == 0:
            p = float("nan")
        else:
            p = float(mannwhitneyu(dentro, fuera, alternative="two-sided").pvalue)
        filas.append({
            "grupo": grupo,
            "n": int(len(dentro)),
            "score_medio": float(dentro.mean()) if len(dentro) else float("nan"),
            "score_mediano": float(dentro.median()) if len(dentro) else float("nan"),
            "p_valor_vs_resto": p,
        })
    return pd.DataFrame(filas)
