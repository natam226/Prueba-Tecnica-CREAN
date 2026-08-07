"""Asignación de niveles de prioridad A/B/C/D por cuartiles (SPEC_V2 §6.2).

Criterio de corte documentado: cuartiles del RANGO PERCENTIL, no de los valores.
Con `pd.qcut` sobre los valores directamente, las masas de empates (muchísimos
scores idénticos y muchos valores esperados en 0) producen bordes duplicados y
el corte falla o queda desbalanceado. El rango percentil con `method="first"`
rompe empates por orden de aparición y garantiza cuatro bloques del 25%.

A = cuartil superior (mayor prioridad), D = cuartil inferior.
"""
import pandas as pd

ETIQUETAS_POR_DEFECTO = ("D", "C", "B", "A")


def asignar_niveles(valores, etiquetas=ETIQUETAS_POR_DEFECTO) -> pd.Series:
    s = pd.Series(valores)
    resultado = pd.Series(pd.NA, index=s.index, dtype=object)
    validos = s.notna()
    if not validos.any():
        return resultado

    rangos = s[validos].rank(method="first", pct=True)
    cortados = pd.cut(
        rangos, bins=[0.0, 0.25, 0.5, 0.75, 1.0],
        labels=list(etiquetas), include_lowest=True,
    )
    resultado.loc[validos] = cortados.astype(object)
    return resultado


def asignar_niveles_por_poblacion(df: pd.DataFrame, col_valor: str,
                                  col_poblacion: str,
                                  etiquetas=ETIQUETAS_POR_DEFECTO) -> pd.Series:
    """Cuartiles calculados DENTRO de cada población por separado."""
    resultado = pd.Series(pd.NA, index=df.index, dtype=object)
    for _, grupo in df.groupby(col_poblacion, dropna=False):
        resultado.loc[grupo.index] = asignar_niveles(grupo[col_valor], etiquetas)
    return resultado
