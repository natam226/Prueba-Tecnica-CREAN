import pytest

from src.fuga import COLUMNAS_FUGA_EXPLICITAS, FugaDeInformacionError
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
    # `_pivotear_producto` dejó de eliminar `fecha_snapshot` para poder
    # derivar `dias_desde_ultimo_dato`, así que estas columnas datetime-string
    # SÍ existen en la tabla real y el fixture debe reflejarlo (ver bug de
    # integración detectado al entrenar: HistGradientBoostingClassifier no puede
    # entrenar con un string de fecha).
    "cdt_fecha_snapshot", "fiducuenta_fecha_snapshot",
    "cuenta_ahorro_fecha_snapshot", "cuenta_corriente_fecha_snapshot",
    "bolsillos_fecha_snapshot", "invesbot_fecha_snapshot",
    "inversion_virtual_fecha_snapshot",
    "dias_desde_ultimo_dato",
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
    # la tabla real cliente_features y debe quedar excluida igual.
    feats = features_modelo_a(COLUMNAS_TIPICAS + ["etiqueta_adopcion_reciente"])
    assert "etiqueta_adopcion_reciente" not in feats


def test_modelo_a_excluye_fecha_snapshot_por_producto():
    # `_pivotear_producto` deja `{producto}_fecha_snapshot` en la tabla (datetime-string) para
    # poder derivar `dias_desde_ultimo_dato`. No es predictora: un modelo de
    # sklearn no puede entrenar con un string de fecha. La forma numérica
    # (`dias_desde_ultimo_dato`) sí debe conservarse.
    feats = features_modelo_a(COLUMNAS_TIPICAS)
    for c in ["cdt_fecha_snapshot", "fiducuenta_fecha_snapshot",
              "cuenta_ahorro_fecha_snapshot", "cuenta_corriente_fecha_snapshot",
              "bolsillos_fecha_snapshot"]:
        assert c not in feats, f"{c} es un artefacto intermedio, no una predictora"
    assert "dias_desde_ultimo_dato" in feats


def test_modelo_a_excluye_toda_columna_de_fuga_explicita_sin_lanzar():
    # Regresión: n_productos_total se agregó a cliente_features. Esa
    # columna ya estaba en fuga.COLUMNAS_FUGA_EXPLICITAS (agrega TODOS los
    # productos, incluidos los de la etiqueta), pero features_modelo nunca la
    # excluía por su cuenta, así que sobrevivía al selector y hacía explotar
    # validar_sin_fuga en lugar de simplemente quedar fuera. La prueba es
    # data-driven sobre fuga.COLUMNAS_FUGA_EXPLICITAS para que una futura
    # adición a ese set quede cubierta automáticamente, sin tener que acordarse
    # de escribir un test nuevo cada vez (que es justo el patrón que falló acá
    # y con etiqueta_adopcion_reciente antes).
    columnas = COLUMNAS_TIPICAS + sorted(COLUMNAS_FUGA_EXPLICITAS)
    feats = features_modelo_a(columnas)  # no debe lanzar FugaDeInformacionError
    for c in COLUMNAS_FUGA_EXPLICITAS:
        assert c not in feats, f"{c} es fuga explícita y debe quedar excluida, no causar un error"


def test_ambas_funciones_lanzan_si_se_cuela_una_columna_prohibida(monkeypatch):
    import src.features_modelo as fm
    # simula un descuido: alguien saca invesbot_ de la lista de no-features
    monkeypatch.setattr(fm, "COLUMNAS_NO_FEATURE", frozenset())
    monkeypatch.setattr(fm, "PREFIJOS_EXCLUIDOS_A", ())
    with pytest.raises(FugaDeInformacionError):
        fm.features_modelo_a(["invesbot_saldo_snapshot", "ingresos_mensuales"])


def test_guard_atrapa_fuga_explicita_aunque_el_filtro_sistematico_falle(monkeypatch):
    # El filtro sistemático (features_modelo_a excluyendo COLUMNAS_FUGA_EXPLICITAS
    # directamente) no debe volver inalcanzable al guard: validar_sin_fuga hace su
    # propia comprobación independiente contra la fuga.COLUMNAS_FUGA_EXPLICITAS
    # real, así que sigue pudiendo fallar aunque la copia local del módulo se
    # vea comprometida (p.ej. por un monkeypatch, o un bug futuro).
    import src.features_modelo as fm
    monkeypatch.setattr(fm, "COLUMNAS_NO_FEATURE", frozenset())
    monkeypatch.setattr(fm, "COLUMNAS_FUGA_EXPLICITAS", frozenset())
    with pytest.raises(FugaDeInformacionError):
        fm.features_modelo_a(["n_productos_total", "ingresos_mensuales"])


def test_modelo_a_excluye_las_columnas_de_fact_cliente_score():
    """Un notebook que hace merge de fact_cliente_score sobre cliente_features
    (p.ej. 07_auditoria_sesgo) no debe arrastrar sus columnas al set de
    predictoras. `nivel` y `poblacion` son strings y rompen el fit; `score` es
    la SALIDA del modelo de propensión y se colaría en silencio como entrada.
    Los nombres del plan (`score_propension`/`nivel_prioridad`) no coinciden con
    los que el notebook escribió realmente (`score`/`nivel`), que es cómo se escapó."""
    columnas_merge = COLUMNAS_TIPICAS + [
        "score", "nivel", "poblacion", "modelo_usado",
        "valor_referencia", "tipo_valor_referencia",
        "valor_esperado_12m", "capacidad_ahorro_anualizada",
    ]
    feats = features_modelo_a(columnas_merge)
    for col in ["score", "nivel", "poblacion", "modelo_usado",
                "valor_referencia", "tipo_valor_referencia",
                "valor_esperado_12m", "capacidad_ahorro_anualizada"]:
        assert col not in feats, f"{col} no puede ser predictora"
    # las legítimas siguen entrando
    assert "ingresos_mensuales" in feats
