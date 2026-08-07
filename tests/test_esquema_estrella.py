import pandas as pd
import pytest

import config
from src.db_io import escribir_tabla_sqlite, leer_tabla_sqlite
from oro.construir_esquema_estrella import construir_esquema_estrella


def test_fact_saldos_mensual_tiene_grano_mensual(tmp_path, monkeypatch):
    """SPEC_V2 §8: fact_saldos_mensual agregado a nivel MENSUAL, no diario."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    escribir_tabla_sqlite(pd.DataFrame({
        "numero_id": [1], "grupo_edad": ["30-39"], "desc_genero": ["F"],
        "desc_segmento": ["PERSONAL"], "desc_tipo_de_vivienda": [None],
    }), plata_db, "clientes_plata")

    cols = ["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
            "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"]
    for t in ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
              "cdt_inversion_virtual_plata", "invesbot_plata"]:
        escribir_tabla_sqlite(pd.DataFrame(columns=cols), plata_db, t)
    escribir_tabla_sqlite(pd.DataFrame([{
        "numero_id": 1, "producto": "cdt", "saldo_snapshot": 10.0,
        "fecha_snapshot": "2026-03-01", "saldo_prom_6m": 10.0,
        "tendencia_6m": 0.0, "n_obs_ventana": 1, "tenencia": 1,
    }]), plata_db, "cdt_inversion_virtual_plata")

    escribir_tabla_sqlite(pd.DataFrame({
        "numero_id": [1, 1, 1],
        "producto": ["cdt", "cdt", "cdt"],
        "mes": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "saldo_mes": [10.0, 10.0, 10.0],
    }), plata_db, "saldos_mensual_plata")

    construir_esquema_estrella()

    fm = leer_tabla_sqlite(oro_db, "fact_saldos_mensual")
    assert len(fm) == 3
    assert not fm.duplicated(subset=["numero_id", "producto_id", "fecha_id"]).any()
    assert fm["producto_id"].notna().all()
    assert fm["fecha_id"].notna().all()

    dt = leer_tabla_sqlite(oro_db, "dim_tiempo")
    dt["fecha"] = pd.to_datetime(dt["fecha"])
    assert (dt["fecha"].dt.day == 1).all(), "dim_tiempo debe tener grano mensual"
    assert dt["fecha_id"].is_unique
    assert set(dt.columns) >= {"fecha_id", "fecha", "anio", "mes", "trimestre"}


def test_dim_cliente_conserva_genero_para_auditoria(tmp_path, monkeypatch):
    """SPEC_V2 §8: dim_cliente incluye desc_genero SOLO para auditoría."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)
    escribir_tabla_sqlite(pd.DataFrame({
        "numero_id": [1], "grupo_edad": ["30-39"], "desc_genero": ["F"],
        "desc_segmento": ["PERSONAL"], "desc_tipo_de_vivienda": ["PROPIA"],
    }), plata_db, "clientes_plata")
    cols = ["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
            "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"]
    for t in ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
              "cdt_inversion_virtual_plata", "invesbot_plata"]:
        escribir_tabla_sqlite(pd.DataFrame(columns=cols), plata_db, t)
    escribir_tabla_sqlite(pd.DataFrame({
        "numero_id": [1], "producto": ["cdt"], "mes": ["2026-01-01"], "saldo_mes": [1.0],
    }), plata_db, "saldos_mensual_plata")

    construir_esquema_estrella()
    dc = leer_tabla_sqlite(oro_db, "dim_cliente")
    assert "desc_genero" in dc.columns
