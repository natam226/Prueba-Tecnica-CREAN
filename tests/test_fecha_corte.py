import pandas as pd

import config
from src.db_io import escribir_tabla_sqlite
from src.fecha_corte import FUENTES_SALDO_CORTE, calcular_fecha_corte


def test_fecha_corte_es_el_minimo_de_los_maximos_por_fuente(tmp_path, monkeypatch):
    bronce_db = tmp_path / "bronce.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)

    # aho_cte llega hasta junio, invesbot hasta mayo: el mínimo de los máximos es mayo.
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [1, 1], "producto": ["CUENTA DE AHORRO"] * 2,
                      "fecha": ["2026-01-01", "2026-06-01"], "saldo": [1.0, 2.0]}),
        bronce_db, "crean_aho_cte")
    for tabla in ["crean_bolsillos", "crean_fiducuenta", "crean_inv_virtual_cdt"]:
        escribir_tabla_sqlite(
            pd.DataFrame({"numero_id": [1], "producto": ["X"],
                          "fecha": ["2026-06-01"], "saldo": [1.0]}),
            bronce_db, tabla)
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [1], "producto": ["INVESBOT"],
                      "fecha": ["2026-05-01"], "saldo": [1.0]}),
        bronce_db, "invesbot")

    assert calcular_fecha_corte(bronce_db) == pd.Timestamp("2026-05-01")


def test_fecha_corte_cubre_las_cinco_fuentes_de_saldo():
    assert set(FUENTES_SALDO_CORTE) == {
        "crean_aho_cte", "crean_bolsillos", "crean_fiducuenta",
        "crean_inv_virtual_cdt", "invesbot",
    }
