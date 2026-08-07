import pytest

from src.fuga import FugaDeInformacionError
from src.features_modelo import (
    COLUMNAS_SENSIBLES_EXCLUIDAS,
    features_modelo_a,
    features_modelo_b,
)

COLUMNAS_TIPICAS = [
    "numero_id", "etiqueta_adopcion", "apto_entrenamiento",
    "tiene_historial_producto", "sin_ninguna_senal", "sin_dato_financiero",
    "sin_dato_financiero_total",
    "ingresos_mensuales", "total_egresos_mensuales", "total_activos",
    "total_pasivos", "total_patrimonio", "capacidad_ahorro",
    "estimador_ingreso", "tiene_estimador_ingreso", "ratio_egreso_ingreso",
    "cdt_saldo_snapshot", "fiducuenta_saldo_snapshot",
    "cuenta_ahorro_saldo_snapshot", "bolsillos_tenencia",
    "n_productos_inversion_no_etiqueta", "saldo_invertido_no_etiqueta",
    "invesbot_saldo_snapshot", "inversion_virtual_tendencia_6m",
    "desc_genero", "grupo_edad", "desc_tipo_de_vivienda", "desc_segmento",
]


def test_modelo_a_excluye_toda_variable_de_la_etiqueta():
    feats = features_modelo_a(COLUMNAS_TIPICAS)
    assert "invesbot_saldo_snapshot" not in feats
    assert "inversion_virtual_tendencia_6m" not in feats
    assert "etiqueta_adopcion" not in feats
    assert "numero_id" not in feats


def test_modelo_a_conserva_productos_que_no_definen_la_etiqueta():
    feats = features_modelo_a(COLUMNAS_TIPICAS)
    for c in ["cdt_saldo_snapshot", "fiducuenta_saldo_snapshot",
              "cuenta_ahorro_saldo_snapshot", "bolsillos_tenencia",
              "n_productos_inversion_no_etiqueta"]:
        assert c in feats


def test_modelo_a_excluye_genero_pero_conserva_edad_y_vivienda():
    # SPEC_V2 §6.4: solo desc_genero queda fuera por criterio de idoneidad
    feats = features_modelo_a(COLUMNAS_TIPICAS)
    assert "desc_genero" not in feats
    assert "grupo_edad" in feats
    assert "desc_tipo_de_vivienda" in feats
    assert COLUMNAS_SENSIBLES_EXCLUIDAS == ("desc_genero",)


def test_modelo_b_no_incluye_ninguna_variable_de_producto():
    feats = features_modelo_b(COLUMNAS_TIPICAS)
    prohibidas = [c for c in feats
                  if "saldo" in c or "tenencia" in c or "productos" in c]
    assert prohibidas == [], f"Modelo B no puede ver productos: {prohibidas}"


def test_modelo_b_conserva_capacidad_financiera_y_derivadas():
    feats = features_modelo_b(COLUMNAS_TIPICAS)
    for c in ["ingresos_mensuales", "total_egresos_mensuales", "total_activos",
              "total_pasivos", "total_patrimonio", "capacidad_ahorro",
              "estimador_ingreso", "ratio_egreso_ingreso"]:
        assert c in feats


def test_modelo_a_excluye_etiqueta_alternativa_de_sensibilidad():
    # D0.2/N4: etiqueta_adopcion_reciente es OTRA etiqueta (ventana alternativa),
    # no una predictora. No está en COLUMNAS_TIPICAS del brief, pero SÍ existe en
    # la tabla real cliente_features (ver Task 3) y debe quedar excluida igual.
    feats = features_modelo_a(COLUMNAS_TIPICAS + ["etiqueta_adopcion_reciente"])
    assert "etiqueta_adopcion_reciente" not in feats


def test_ambas_funciones_lanzan_si_se_cuela_una_columna_prohibida(monkeypatch):
    import src.features_modelo as fm
    # simula un descuido: alguien saca invesbot_ de la lista de no-features
    monkeypatch.setattr(fm, "COLUMNAS_NO_FEATURE", frozenset())
    monkeypatch.setattr(fm, "PREFIJOS_EXCLUIDOS_A", ())
    with pytest.raises(FugaDeInformacionError):
        fm.features_modelo_a(["invesbot_saldo_snapshot", "ingresos_mensuales"])
