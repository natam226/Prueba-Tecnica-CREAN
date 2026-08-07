"""Export final para Power BI (SPEC_V2 §8).

Produce los 8 archivos de la tabla de §8. Los que generan los notebooks
(fact_auditoria_sesgo, dimensionamiento) no se regeneran aquí: se verifica su
presencia y se reporta su conteo de filas, para que el export sea la única
comprobación de que el entregable está completo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import config
from src.db_io import leer_tabla_sqlite

# Tablas que salen directamente de oro.db
TABLAS_ORO = {
    "fact_cliente_score": "fact_cliente_score",
    "dim_cliente": "dim_cliente",
    "dim_producto": "dim_producto",
    "dim_tiempo": "dim_tiempo",
    "fact_saldos_mensual": "fact_saldos_mensual",
}

# Archivos que producen los notebooks y aquí solo se verifican
GENERADOS_POR_NOTEBOOKS = ["fact_auditoria_sesgo.csv", "dimensionamiento.csv"]


def construir_fact_importancia_variables(validacion: pd.DataFrame,
                                         importancia: pd.DataFrame) -> pd.DataFrame:
    """SPEC_V2 §8: variable, importancia, IV, decisión de inclusión.

    Outer join: las variables descartadas por IV no aparecen en la importancia
    de permutación (no entraron al modelo) y las dummies generadas por
    get_dummies no tienen IV propio. Las dos situaciones deben quedar visibles
    en el entregable, no desaparecer por un inner join.
    """
    cols_val = [c for c in ["variable", "iv", "clase_iv", "vif", "q_bh",
                            "significativa_fdr", "decision_inclusion"]
                if c in validacion.columns]
    r = importancia.merge(validacion[cols_val], on="variable", how="outer")
    return r.sort_values(["modelo", "importancia"], ascending=[True, False],
                         na_position="last").reset_index(drop=True)


def main():
    destino = config.OUTPUTS_DIR / "powerbi"
    destino.mkdir(parents=True, exist_ok=True)
    reporte = {}

    for nombre, tabla in TABLAS_ORO.items():
        df = leer_tabla_sqlite(config.ORO_DB, tabla)
        ruta = destino / f"{nombre}.csv"
        df.to_csv(ruta, index=False)
        reporte[f"{nombre}.csv"] = len(df)
        print(f"{nombre}.csv: {len(df):,} filas")

    # fact_importancia_variables: IV (notebook 04) + permutation importance (notebook 02)
    ruta_val = config.OUTPUTS_DIR / "eda" / "validacion_variables.csv"
    ruta_imp = config.OUTPUTS_DIR / "models" / "importancia_permutacion.csv"
    if ruta_val.exists() and ruta_imp.exists():
        fiv = construir_fact_importancia_variables(
            pd.read_csv(ruta_val), pd.read_csv(ruta_imp))
        fiv.to_csv(destino / "fact_importancia_variables.csv", index=False)
        reporte["fact_importancia_variables.csv"] = len(fiv)
        print(f"fact_importancia_variables.csv: {len(fiv):,} filas")
    else:
        faltan = [str(p) for p in [ruta_val, ruta_imp] if not p.exists()]
        raise FileNotFoundError(
            f"faltan insumos de fact_importancia_variables: {faltan}. "
            "Ejecutar antes notebooks/04_validacion_variables.ipynb y 02_modelado.ipynb"
        )

    for nombre in GENERADOS_POR_NOTEBOOKS:
        ruta = destino / nombre
        if not ruta.exists():
            raise FileNotFoundError(
                f"{nombre} no existe. Lo produce un notebook: "
                "07_auditoria_sesgo.ipynb / 05_dimensionamiento.ipynb"
            )
        reporte[nombre] = len(pd.read_csv(ruta))
        print(f"{nombre}: {reporte[nombre]:,} filas (generado por notebook)")

    with open(destino / "reporte_export.json", "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    # SPEC_V2 §8: reportar el conteo de filas de fact_saldos_mensual tras la
    # agregación mensual, y comprobar que el volumen es razonable.
    n_mensual = reporte["fact_saldos_mensual.csv"]
    print(f"\nSPEC_V2 §8 — fact_saldos_mensual tras agregación mensual: {n_mensual:,} filas")
    assert n_mensual < 30_000_000, f"volumen desproporcionado: {n_mensual:,}"
    print(f"Export completo: {len(reporte)} archivos en {destino}")


if __name__ == "__main__":
    main()
