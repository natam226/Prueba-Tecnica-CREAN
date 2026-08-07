"""Batería de validación estadística de variables (SPEC_V2 §4).

Objetivo: poder justificar la inclusión o exclusión de cada variable con un
criterio explícito, no por intuición.
"""
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu
from sklearn.linear_model import LinearRegression

ETIQUETA_NULOS = "Sin dato"
# Corrección de Haldane-Anscombe: evita log(0) en bins sin eventos o sin no-eventos.
EPS = 0.5


def binear(x, n_bins: int = 10, etiqueta_nulos: str = ETIQUETA_NULOS) -> pd.Series:
    """Bins por cuantiles para continuas, categorías tal cual para el resto.

    Los nulos se convierten SIEMPRE en un bin propio con etiqueta `etiqueta_nulos`
    (SPEC_V2 §4: "calcular el IV tratando 'Sin dato' como un bin más").
    `duplicates="drop"` es indispensable: los saldos tienen masas enormes en 0 y
    varios bordes de cuantil coinciden. Cuando esa masa es tan grande que ni
    siquiera sobrevive un solo borde interno (p. ej. >90% de los valores son 0),
    `qcut` colapsa todo en un único bin; en ese caso se separa el valor
    dominante (la moda) en su propio bin y se cuantiliza el resto por separado,
    para no perder toda capacidad discriminante de la variable.
    """
    s = pd.Series(x)
    es_numerica = s.dtype.kind in "biufc"
    if not (es_numerica and s.nunique(dropna=True) > n_bins):
        out = s.astype(object)
        return out.where(out.notna(), etiqueta_nulos)

    mask_nulo = s.isna()
    valores = s[~mask_nulo]
    binned = pd.qcut(valores, q=n_bins, duplicates="drop").astype(object)

    if binned.nunique(dropna=True) < 2 and valores.nunique() > 1:
        moda = valores.mode().iloc[0]
        es_moda = valores == moda
        resto = valores[~es_moda]
        out_validos = pd.Series(index=valores.index, dtype=object)
        out_validos.loc[valores.index[es_moda]] = f"= {moda}"
        if resto.nunique() > 1:
            n_bins_resto = min(n_bins, resto.nunique())
            out_validos.loc[resto.index] = pd.qcut(
                resto, q=n_bins_resto, duplicates="drop"
            ).astype(object)
        elif resto.nunique() == 1:
            out_validos.loc[resto.index] = resto.astype(object)
    else:
        out_validos = binned

    out = pd.Series(index=s.index, dtype=object)
    out.loc[out_validos.index] = out_validos
    out.loc[mask_nulo] = etiqueta_nulos
    return out


def calcular_woe_iv(x, y, n_bins: int = 10,
                    etiqueta_nulos: str = ETIQUETA_NULOS):
    """Information Value y WoE por bin.

    Convención: WoE = ln(%no_eventos / %eventos). El signo depende de la
    convención elegida; el IV es invariante a ella.
    """
    bins = binear(x, n_bins=n_bins, etiqueta_nulos=etiqueta_nulos)
    y = pd.Series(y).astype(int).reset_index(drop=True)
    tab = pd.DataFrame({"bin": bins.reset_index(drop=True).astype(str), "y": y})

    g = tab.groupby("bin", as_index=False)["y"].agg(n="count", eventos="sum")
    g["no_eventos"] = g["n"] - g["eventos"]

    tot_e = g["eventos"].sum()
    tot_ne = g["no_eventos"].sum()
    k = len(g)
    g["pct_eventos"] = (g["eventos"] + EPS) / (tot_e + EPS * k)
    g["pct_no_eventos"] = (g["no_eventos"] + EPS) / (tot_ne + EPS * k)
    g["woe"] = np.log(g["pct_no_eventos"] / g["pct_eventos"])
    g["iv_bin"] = (g["pct_no_eventos"] - g["pct_eventos"]) * g["woe"]

    return float(g["iv_bin"].sum()), g


def clasificar_iv(iv: float) -> str:
    """Cortes estándar de scorecard bancario (SPEC_V2 §4.1)."""
    if iv < 0.02:
        return "descartar"
    if iv < 0.10:
        return "debil"
    if iv < 0.30:
        return "media"
    return "fuerte"


def mann_whitney(x, y) -> dict:
    """Mann-Whitney U para continuas vs. etiqueta (SPEC_V2 §4.2).

    No t-test: los datos financieros son fuertemente asimétricos y el t-test
    asume normalidad de las medias muestrales por grupo.
    """
    s = pd.Series(x).reset_index(drop=True)
    yy = pd.Series(y).astype(int).reset_index(drop=True)
    g1 = s[yy == 1].dropna()
    g0 = s[yy == 0].dropna()
    if len(g1) == 0 or len(g0) == 0:
        return {"u": float("nan"), "p_valor": float("nan"),
                "mediana_evento": float("nan"), "mediana_no_evento": float("nan"),
                "n_evento": int(len(g1)), "n_no_evento": int(len(g0))}
    u, p = mannwhitneyu(g1, g0, alternative="two-sided")
    return {"u": float(u), "p_valor": float(p),
            "mediana_evento": float(g1.median()),
            "mediana_no_evento": float(g0.median()),
            "n_evento": int(len(g1)), "n_no_evento": int(len(g0))}


def chi2_y_cramer(x, y, etiqueta_nulos: str = ETIQUETA_NULOS) -> dict:
    """Chi-cuadrado de independencia + V de Cramér (SPEC_V2 §4.3)."""
    xs = pd.Series(x).astype(object)
    xs = xs.where(xs.notna(), etiqueta_nulos)
    tabla = pd.crosstab(xs.reset_index(drop=True), pd.Series(y).reset_index(drop=True))
    if tabla.shape[0] < 2 or tabla.shape[1] < 2:
        return {"chi2": float("nan"), "p_valor": float("nan"),
                "gl": 0, "v_cramer": float("nan")}
    chi2, p, gl, _ = chi2_contingency(tabla)
    n = tabla.to_numpy().sum()
    k = min(tabla.shape) - 1
    v = float(np.sqrt(chi2 / (n * k))) if k > 0 else float("nan")
    return {"chi2": float(chi2), "p_valor": float(p), "gl": int(gl), "v_cramer": v}


def benjamini_hochberg(p_valores, alpha: float = 0.05):
    """Corrección FDR de Benjamini-Hochberg (SPEC_V2 §4.4).

    Devuelve (q_valores, rechaza). Se prueban decenas de variables a la vez: sin
    corregir, con 40 pruebas a alpha=0.05 se esperan ~2 "significativas" por azar.
    """
    p = np.asarray(p_valores, dtype=float)
    if np.isnan(p).any():
        raise ValueError("benjamini_hochberg no admite p-valores NaN; fíltralos antes")
    n = len(p)
    if n == 0:
        return np.array([]), np.array([], dtype=bool)

    orden = np.argsort(p)
    p_ord = p[orden]
    q_ord = p_ord * n / np.arange(1, n + 1)
    q_ord = np.minimum.accumulate(q_ord[::-1])[::-1]   # monotonía sobre p
    q_ord = np.minimum(q_ord, 1.0)

    q = np.empty(n, dtype=float)
    q[orden] = q_ord
    return q, q <= alpha


def calcular_vif(df_numerico: pd.DataFrame) -> pd.DataFrame:
    """VIF por variable (SPEC_V2 §4.5). Umbral de alerta: VIF > 10.

    VIF_j = 1 / (1 − R²_j), con R²_j la regresión de la variable j sobre el resto.
    """
    X = df_numerico.replace([np.inf, -np.inf], np.nan).dropna()
    filas = []
    for col in X.columns:
        otras = X.drop(columns=[col])
        if otras.shape[1] == 0 or X.shape[0] <= otras.shape[1]:
            filas.append({"variable": col, "vif": float("nan")})
            continue
        r2 = LinearRegression().fit(otras, X[col]).score(otras, X[col])
        vif = float("inf") if r2 >= 1 - 1e-12 else 1.0 / (1.0 - r2)
        filas.append({"variable": col, "vif": float(vif)})
    return pd.DataFrame(filas)
