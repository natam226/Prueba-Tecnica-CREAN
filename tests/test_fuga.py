import pytest

from src.fuga import (
    FugaDeInformacionError,
    columnas_con_fuga,
    validar_sin_fuga,
)


def test_falla_con_prefijo_invesbot():
    with pytest.raises(FugaDeInformacionError, match="invesbot_saldo_snapshot"):
        validar_sin_fuga(["ingresos_mensuales", "invesbot_saldo_snapshot"])


def test_falla_con_ambas_grafias_de_inversion_virtual():
    # SPEC_V2 escribe `inv_virtual_`; el código de plata/oro genera `inversion_virtual_`.
    # El guard debe atrapar las dos.
    with pytest.raises(FugaDeInformacionError):
        validar_sin_fuga(["inv_virtual_saldo_prom_6m"])
    with pytest.raises(FugaDeInformacionError):
        validar_sin_fuga(["inversion_virtual_tendencia_6m"])


def test_falla_con_agregados_que_suman_productos_de_la_etiqueta():
    # No llevan prefijo, pero suman Invesbot/IV por definición (SPEC_V2 §1)
    for col in [
        "n_productos_inversion",
        "saldo_total_invertido",
        "pct_patrimonio_invertido",
        "n_productos_total",
        "tiene_invesbot",
        "tiene_inv_virtual",
        "tiene_historial_inversion",
        "etiqueta_adopcion",
    ]:
        with pytest.raises(FugaDeInformacionError):
            validar_sin_fuga(["ingresos_mensuales", col])


def test_acepta_las_derivadas_no_etiqueta():
    # Estas SÍ son predictoras legítimas: solo suman CDT y Fiducuenta
    assert validar_sin_fuga([
        "ingresos_mensuales",
        "cdt_saldo_snapshot",
        "fiducuenta_saldo_snapshot",
        "n_productos_inversion_no_etiqueta",
        "saldo_invertido_no_etiqueta",
        "n_productos_no_etiqueta",
    ])


def test_columnas_con_fuga_devuelve_todas_ordenadas():
    encontradas = columnas_con_fuga(
        ["ingresos_mensuales", "invesbot_tenencia", "etiqueta_adopcion"]
    )
    assert encontradas == ["etiqueta_adopcion", "invesbot_tenencia"]


def test_el_mensaje_de_error_nombra_el_contexto():
    with pytest.raises(FugaDeInformacionError, match="Modelo B"):
        validar_sin_fuga(["invesbot_tenencia"], contexto="Modelo B")
