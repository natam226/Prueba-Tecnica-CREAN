import pandas as pd
import pytest

import config
from src.db_io import leer_tabla_sqlite
from bronce.diagnostico_calidad import (
    verificar_unicidad_cliente,
    verificar_unicidad_producto_fecha,
)

TABLAS_SALDO = ["crean_aho_cte", "crean_bolsillos", "crean_fiducuenta",
                "crean_inv_virtual_cdt", "invesbot"]
TABLAS_PLATA_PRODUCTO = ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
                         "cdt_inversion_virtual_plata", "invesbot_plata"]


def test_verificar_unicidad_producto_fecha_detecta_duplicados():
    df = pd.DataFrame({
        "numero_id": [1, 1], "producto": ["CDT", "CDT"],
        "fecha": ["2026-01-01", "2026-01-01"], "saldo": [1.0, 2.0],
    })
    r = verificar_unicidad_producto_fecha(df, "sintetica")
    assert r["duplicados"] == 1
    assert r["unico"] is False


def test_verificar_unicidad_producto_fecha_acepta_grano_correcto():
    df = pd.DataFrame({
        "numero_id": [1, 1], "producto": ["CDT", "CDT"],
        "fecha": ["2026-01-01", "2026-02-01"], "saldo": [1.0, 2.0],
    })
    assert verificar_unicidad_producto_fecha(df, "sintetica")["unico"] is True


def test_verificar_unicidad_producto_fecha_columna_ausente_no_se_marca_como_verificado():
    """Si falta 'producto' o 'fecha', el chequeo no puede realizarse: debe ser
    distinguible de una verificación real que pasó, no un falso 'unico=True'."""
    df = pd.DataFrame({"numero_id": [1, 1], "saldo": [1.0, 2.0]})  # sin producto ni fecha
    r = verificar_unicidad_producto_fecha(df, "sintetica")
    assert r["verificado"] is False
    assert r["unico"] is None
    assert "producto" in r["nota"] and "fecha" in r["nota"]


def test_verificar_unicidad_cliente():
    assert verificar_unicidad_cliente(pd.DataFrame({"numero_id": [1, 2]}), "t")["unico"] is True
    assert verificar_unicidad_cliente(pd.DataFrame({"numero_id": [1, 1]}), "t")["unico"] is False


@pytest.mark.skipif(not config.BRONCE_DB.exists(), reason="bronce.db no construido")
@pytest.mark.parametrize("tabla", TABLAS_SALDO)
def test_bronce_unico_por_cliente_producto_fecha(tabla):
    """SPEC_V2 §9.1"""
    r = verificar_unicidad_producto_fecha(leer_tabla_sqlite(config.BRONCE_DB, tabla), tabla)
    # r["unico"] es None si el chequeo no pudo ejecutarse (falta una columna clave) y
    # False si se ejecutó y encontró duplicados; en ambos casos debe fallar, no pasar en silencio.
    assert r["unico"], (
        f"{tabla}: verificado={r.get('verificado')}, duplicados={r['duplicados']}, "
        f"nota={r.get('nota', '(sin nota, se ejecutó el chequeo)')}"
    )


@pytest.mark.skipif(not config.ORO_DB.exists(), reason="oro.db no construido")
def test_cliente_features_unico_por_cliente():
    """SPEC_V2 §9.2"""
    cf = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
    cp = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")
    assert verificar_unicidad_cliente(cf, "cliente_features")["unico"]
    assert len(cf) == cp["numero_id"].nunique()


@pytest.mark.skipif(not config.PLATA_DB.exists(), reason="plata.db no construido")
@pytest.mark.parametrize("tabla", TABLAS_PLATA_PRODUCTO)
def test_plata_una_fila_por_cliente_producto(tabla):
    """SPEC_V2 §9.3"""
    df = leer_tabla_sqlite(config.PLATA_DB, tabla)
    dup = int(df.duplicated(subset=["numero_id", "producto"]).sum())
    assert dup == 0, f"{tabla}: {dup} filas extra por cliente-producto"
