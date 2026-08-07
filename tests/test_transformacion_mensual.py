# tests/test_transformacion_mensual.py
import pandas as pd

import config
from src.db_io import escribir_tabla_sqlite, leer_tabla_sqlite
from plata.transformacion import construir_saldos_mensual, construir_primer_registro


def _bronce_minimo(bronce_db):
    escribir_tabla_sqlite(
        pd.DataFrame({
            "fecha": ["2026-01-10", "2026-03-05"],
            "numero_id": [1, 1],
            "producto": ["CUENTA DE AHORRO", "CUENTA DE AHORRO"],
            "saldo": [100.0, 300.0],
        }),
        bronce_db, "crean_aho_cte",
    )
    for tabla, producto in [("crean_bolsillos", "BOLSILLOS"),
                            ("crean_fiducuenta", "FIDUCUENTA"),
                            ("invesbot", "INVESBOT")]:
        escribir_tabla_sqlite(
            pd.DataFrame({"fecha": ["2026-02-01"], "numero_id": [2],
                          "producto": [producto], "saldo": [50.0]}),
            bronce_db, tabla,
        )
    escribir_tabla_sqlite(
        pd.DataFrame({"fecha": ["2026-03-01"], "numero_id": [1],
                      "producto": ["CDT"], "saldo": [7.0]}),
        bronce_db, "crean_inv_virtual_cdt",
    )


def test_saldos_mensual_aplica_forward_fill_por_cliente_producto(tmp_path, monkeypatch):
    bronce_db = tmp_path / "bronce.db"
    plata_db = tmp_path / "plata.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    _bronce_minimo(bronce_db)

    construir_saldos_mensual()
    r = leer_tabla_sqlite(plata_db, "saldos_mensual_plata")
    r["mes"] = pd.to_datetime(r["mes"])

    # D4: FECHA_CORTE = min(max_fecha por fuente) = 2026-02-01 en este fixture
    # (bolsillos/fiducuenta/invesbot solo tienen dato hasta esa fecha). El dato
    # de aho_cte del 2026-03-05 queda POR ENCIMA del corte y no debe usarse:
    # ninguna fuente se regulariza más allá de lo que ven las demás.
    ahorro = r[(r["numero_id"] == 1) & (r["producto"] == "cuenta_ahorro")].sort_values("mes")
    assert ahorro["mes"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")]
    assert ahorro["saldo_mes"].tolist() == [100.0, 100.0]   # ene (real), feb (ffill)
    assert ahorro["observado"].tolist() == [1, 0]
    # `cdt` (fuente crean_inv_virtual_cdt) solo tiene una fila, en 2026-03-01,
    # que queda POR ENCIMA del corte global (2026-02-01). Por el contrato de
    # frontera de `construir_panel_mensual` (Task 6, ver src/panel_mensual.py):
    # un grupo cuyo primer mes real es POSTERIOR a mes_max se omite del panel
    # por completo (cero filas) — no se inventa una fila con un saldo que
    # nunca existió antes del corte. Por eso `cdt` NO aparece en este fixture.
    assert set(r["producto"]) == {"cuenta_ahorro", "bolsillos", "fiducuenta", "invesbot"}
    assert r[r["producto"] == "cdt"].empty
    assert not r.duplicated(subset=["numero_id", "producto", "mes"]).any()
    assert r["mes"].max() == pd.Timestamp("2026-02-01")   # ninguna fuente pasa del corte global


def test_primer_registro_toma_el_minimo_entre_todas_las_fuentes(tmp_path, monkeypatch):
    bronce_db = tmp_path / "bronce.db"
    plata_db = tmp_path / "plata.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    _bronce_minimo(bronce_db)

    construir_primer_registro()
    r = leer_tabla_sqlite(plata_db, "primer_registro_plata").set_index("numero_id")
    assert pd.Timestamp(r.loc[1, "primer_mes"]) == pd.Timestamp("2026-01-01")
    assert pd.Timestamp(r.loc[2, "primer_mes"]) == pd.Timestamp("2026-02-01")
