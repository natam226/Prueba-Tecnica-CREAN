import numpy as np
import pytest

from src.decisiones import (
    decidir_interpretacion_proxy_genero,
    decidir_perfil_incompleto,
    decidir_tratamiento_faltante_estimador,
    decidir_tratamiento_vivienda,
    lift_condicional,
)


# --- SPEC_V2 §3.2: la acción depende del AUC obtenido, no de una elección previa ---

def test_auc_bajo_ausencia_aleatoria_modelo_maneja_nulos():
    r = decidir_tratamiento_faltante_estimador(0.53, modelo_maneja_nulos=True)
    assert r["conclusion"] == "ausencia aproximadamente aleatoria"
    assert r["accion"] == "conservar_bandera_sin_imputar"
    assert r["imputar"] is False
    assert r["documentar_variables_asociadas"] is False


def test_auc_bajo_ausencia_aleatoria_modelo_no_maneja_nulos():
    r = decidir_tratamiento_faltante_estimador(0.53, modelo_maneja_nulos=False)
    assert r["accion"] == "conservar_bandera_e_imputar_mediana_segmento"
    assert r["imputar"] is True


def test_auc_intermedio_patron_debil_documenta_variables():
    r = decidir_tratamiento_faltante_estimador(0.65, modelo_maneja_nulos=True)
    assert r["conclusion"] == "patrón débil"
    assert r["accion"] == "conservar_bandera_sin_imputar"
    assert r["documentar_variables_asociadas"] is True


def test_auc_alto_ausencia_informativa_no_imputa_con_medida_central_global():
    r = decidir_tratamiento_faltante_estimador(0.83, modelo_maneja_nulos=True)
    assert r["conclusion"] == "ausencia informativa"
    assert r["accion"] == "bandera_predictora_sin_imputacion_global"
    assert r["bandera_como_predictora"] is True
    assert r["documentar_variables_asociadas"] is True


def test_auc_alto_nunca_imputa_media_global_aunque_el_modelo_no_maneje_nulos():
    r = decidir_tratamiento_faltante_estimador(0.83, modelo_maneja_nulos=False)
    assert r["accion"] == "bandera_predictora_sin_imputacion_global"


@pytest.mark.parametrize("auc,esperado", [
    (0.599, "ausencia aproximadamente aleatoria"),
    (0.600, "patrón débil"),      # los bordes 0.60 y 0.70 caen en la banda intermedia
    (0.700, "patrón débil"),
    (0.701, "ausencia informativa"),
])
def test_bordes_de_la_tabla_de_decision(auc, esperado):
    assert decidir_tratamiento_faltante_estimador(auc)["conclusion"] == esperado


def test_auc_invalido_lanza():
    with pytest.raises(ValueError):
        decidir_tratamiento_faltante_estimador(1.4)


# --- SPEC_V2 §6.5: regla de decisión de tipo de vivienda ---

def test_vivienda_iv_categorica_suficiente_conserva_la_categorica():
    r = decidir_tratamiento_vivienda(iv_categorica=0.031, iv_bandera=0.004)
    assert r["accion"] == "conservar_categorica_con_sin_dato"
    assert r["conservar_categorica"] is True
    assert r["conservar_bandera"] is False


def test_vivienda_solo_la_bandera_aporta():
    r = decidir_tratamiento_vivienda(iv_categorica=0.011, iv_bandera=0.045)
    assert r["accion"] == "descartar_categorica_conservar_bandera"
    assert r["conservar_categorica"] is False
    assert r["conservar_bandera"] is True


def test_vivienda_ninguna_supera_el_umbral_se_descarta_todo():
    r = decidir_tratamiento_vivienda(iv_categorica=0.005, iv_bandera=0.009)
    assert r["accion"] == "descartar_por_completo"
    assert r["conservar_categorica"] is False
    assert r["conservar_bandera"] is False


def test_vivienda_umbral_exacto_conserva():
    assert decidir_tratamiento_vivienda(0.02, 0.0)["conservar_categorica"] is True


# --- SPEC_V2 §5 / §6.5.2: bandera única perfil_incompleto (D7: lift, no Jaccard) ---

def test_lift_condicional_mayor_que_uno_indica_causa_comun():
    """D7: lift = P(sin_b | sin_a) / P(sin_b | con_a). Universo de 20: 10 sin_a,
    de los cuales 8 también están en sin_b (P=0.8); de los 10 con_a, 2 están en
    sin_b (P=0.2). lift = 0.8/0.2 = 4.0 -> fuerte causa común."""
    universo = set(range(20))
    sin_a = set(range(10))
    sin_b = set(range(8)) | {10, 11}   # 8 dentro de sin_a, 2 fuera
    assert lift_condicional(sin_a, sin_b, universo) == pytest.approx(4.0)


def test_lift_condicional_uno_indica_independencia():
    universo = set(range(20))
    sin_a = set(range(10))
    sin_b = set(range(0, 20, 2))   # mitad de cada grupo, independiente de sin_a
    assert lift_condicional(sin_a, sin_b, universo) == pytest.approx(1.0)


def test_lift_condicional_con_a_vacio_o_universo_igual_a_sin_a_es_nan():
    universo = {1, 2, 3}
    assert np.isnan(lift_condicional(set(), {1}, universo))       # sin_a vacío
    assert np.isnan(lift_condicional(universo, {1}, universo))    # con_a vacío


def test_lift_condicional_con_a_sin_ningun_caso_de_b_es_cero():
    universo = set(range(10))
    sin_a = set(range(5))
    sin_b = set()   # nadie sin_b -> P(sin_b|sin_a) = 0
    assert lift_condicional(sin_a, sin_b, universo) == 0.0


def test_perfil_incompleto_se_crea_si_el_lift_es_alto():
    """D7: UMBRAL_LIFT_PERFIL_INCOMPLETO = 1.5 (config.py)."""
    assert decidir_perfil_incompleto(2.4)["crear_bandera_unica"] is True
    assert decidir_perfil_incompleto(1.1)["crear_bandera_unica"] is False
    assert decidir_perfil_incompleto(1.5)["crear_bandera_unica"] is True   # umbral inclusive


# --- SPEC_V2 §6.6.1: bandas de interpretación del proxy de género (D6) ---

def test_proxy_genero_bajo_0_60_es_minimo():
    r = decidir_interpretacion_proxy_genero(0.55)
    assert r["interpretacion"] == "proxy mínimo"
    assert r["accion"] == "documentar_y_continuar"


def test_proxy_genero_entre_0_60_y_0_70_es_moderado():
    r = decidir_interpretacion_proxy_genero(0.65)
    assert r["interpretacion"] == "proxy moderado"
    assert r["accion"] == "documentar_variables_asociadas"


def test_proxy_genero_sobre_0_70_es_sustancial():
    r = decidir_interpretacion_proxy_genero(0.85)
    assert r["interpretacion"] == "proxy sustancial"
    assert r["accion"] == "investigar_mitigacion"


def test_proxy_genero_bordes_de_las_bandas():
    assert decidir_interpretacion_proxy_genero(0.60)["interpretacion"] == "proxy moderado"
    assert decidir_interpretacion_proxy_genero(0.70)["interpretacion"] == "proxy moderado"
    assert decidir_interpretacion_proxy_genero(0.701)["interpretacion"] == "proxy sustancial"
