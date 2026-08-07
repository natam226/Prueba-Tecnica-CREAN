import pandas as pd

from scripts.export_powerbi import construir_fact_importancia_variables


def test_fact_importancia_une_iv_e_importancia_de_permutacion():
    """SPEC_V2 §8: fact_importancia_variables = variable, importancia, IV, decisión."""
    validacion = pd.DataFrame({
        "variable": ["ingresos_mensuales", "ratio_pasivo_activo", "cdt_saldo_snapshot"],
        "iv": [0.45, 0.01, 0.22],
        "clase_iv": ["fuerte", "descartar", "media"],
        "decision_inclusion": ["incluir", "descartar_iv_insuficiente", "incluir"],
    })
    importancia = pd.DataFrame({
        "variable": ["ingresos_mensuales", "cdt_saldo_snapshot", "desc_segmento_PYME"],
        "importancia": [0.09, 0.04, 0.01],
        "modelo": ["A", "A", "A"],
    })
    r = construir_fact_importancia_variables(validacion, importancia)

    assert set(r.columns) >= {"variable", "importancia", "iv", "decision_inclusion", "modelo"}
    fila = r.set_index(["variable", "modelo"]).loc[("ingresos_mensuales", "A")]
    assert fila["iv"] == 0.45
    assert fila["importancia"] == 0.09
    # una variable con IV pero sin importancia (descartada) sigue apareciendo
    assert "ratio_pasivo_activo" in set(r["variable"])
    # una dummy sin IV propio también aparece, con IV nulo
    dummy = r[r["variable"] == "desc_segmento_PYME"]
    assert len(dummy) == 1
    assert pd.isna(dummy["iv"].iloc[0])
