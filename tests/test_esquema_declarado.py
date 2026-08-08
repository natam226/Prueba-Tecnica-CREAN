"""El esquema de oro está declarado y la base lo hace cumplir.

Durante buena parte del proyecto la integridad de oro se sostuvo solo en estas
pruebas: `pandas.to_sql` crea tablas sin llaves, sin NOT NULL y sin índices.
Ahora las restricciones están en la base, y estas pruebas verifican que sigan
ahí y que efectivamente rechacen lo que deben rechazar.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oro import esquema
from src.db_io import escribir_tabla_sqlite


def _tabla(**columnas):
    return pd.DataFrame(columnas)


# --------------------------------------------------------------- generación
def test_los_tipos_de_fecha_se_reconocen_en_cualquier_unidad():
    """pandas 3 nombra las fechas `datetime64[us]` y pandas 2 `datetime64[ns]`.

    Una tabla de equivalencias exacta mandaba las fechas a TEXT sin avisar; el
    fallo era silencioso y solo se veía leyendo el DDL generado.
    """
    for unidad in ["ns", "us", "ms", "s"]:
        serie = pd.Series(pd.to_datetime(["2025-06-01"])).astype(f"datetime64[{unidad}]")
        assert esquema._tipo_sql(serie) == "TIMESTAMP", unidad


@pytest.mark.parametrize("valores, esperado", [
    (pd.Series([1, 2], dtype="int64"), "INTEGER"),
    (pd.Series([1.5], dtype="float64"), "REAL"),
    (pd.Series([True]), "INTEGER"),
    (pd.Series(["a"]), "TEXT"),
])
def test_mapeo_de_tipos(valores, esperado):
    assert esquema._tipo_sql(valores) == esperado


def test_la_llave_primaria_simple_implica_not_null():
    ddl = esquema.ddl(_tabla(id=[1], x=["a"]), "t", pk="id")
    assert "PRIMARY KEY" in ddl
    assert '"id" INTEGER NOT NULL PRIMARY KEY' in ddl or '"id" INTEGER PRIMARY KEY' in ddl


def test_llave_compuesta_y_foraneas():
    ddl = esquema.ddl(
        _tabla(a=[1], b=[1], v=[1.0]), "t", pk=["a", "b"],
        fks=[("a", "dim", "a")])
    assert 'PRIMARY KEY ("a", "b")' in ddl
    assert 'FOREIGN KEY ("a") REFERENCES "dim" ("a")' in ddl


def test_todas_las_tablas_de_oro_declaran_llave():
    for tabla, reglas in esquema.RESTRICCIONES.items():
        assert reglas.get("pk"), f"{tabla} no declara llave primaria"


# ------------------------------------------------------------- cumplimiento
def _falla_por_integridad(fn) -> bool:
    """La escritura falla y la causa de fondo es una violación de integridad.

    pandas envuelve el `sqlite3.IntegrityError` en su propio `DatabaseError`,
    así que hay que mirar la causa encadenada: comprobar solo el tipo externo
    dejaría pasar cualquier otro fallo de escritura como si fuera la
    restricción actuando.
    """
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - se inspecciona la cadena completa
        while e is not None:
            if isinstance(e, sqlite3.IntegrityError):
                return True
            e = e.__cause__
    return False


def test_la_llave_primaria_rechaza_duplicados(tmp_path):
    db = tmp_path / "t.db"
    datos = _tabla(numero_id=[1, 1], score=[0.5, 0.6])
    ddl = esquema.ddl(datos, "cliente", pk="numero_id")
    assert _falla_por_integridad(
        lambda: escribir_tabla_sqlite(datos, db, "cliente", ddl=ddl))


def test_not_null_rechaza_nulos(tmp_path):
    db = tmp_path / "t.db"
    datos = _tabla(numero_id=[1, 2], score=[0.5, None])
    ddl = esquema.ddl(datos, "cliente", pk="numero_id", no_nulos=["score"])
    assert _falla_por_integridad(
        lambda: escribir_tabla_sqlite(datos, db, "cliente", ddl=ddl))


def test_una_escritura_valida_no_falla(tmp_path):
    """Contrapeso: sin esto, un DDL roto haria pasar las dos pruebas de arriba."""
    db = tmp_path / "t.db"
    datos = _tabla(numero_id=[1, 2], score=[0.5, 0.6])
    ddl = esquema.ddl(datos, "cliente", pk="numero_id", no_nulos=["score"])
    escribir_tabla_sqlite(datos, db, "cliente", ddl=ddl)
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM cliente").fetchone()[0] == 2
    finally:
        con.close()


def test_sin_ddl_pandas_no_declara_nada(tmp_path):
    """Deja constancia de por qué hace falta el DDL explícito.

    Si esta prueba empezara a fallar seria porque pandas cambio de conducta, y
    entonces habria que revisar si el modulo `esquema` sigue haciendo falta.
    """
    db = tmp_path / "t.db"
    escribir_tabla_sqlite(_tabla(numero_id=[1, 1]), db, "sin_reglas")
    con = sqlite3.connect(db)
    try:
        info = list(con.execute('PRAGMA table_info("sin_reglas")'))
    finally:
        con.close()
    assert not any(r[5] for r in info), "pandas ahora sí declara llave primaria"
    assert not any(r[3] for r in info), "pandas ahora sí declara NOT NULL"


def test_los_indices_se_crean(tmp_path):
    db = tmp_path / "t.db"
    datos = _tabla(numero_id=[1, 2], poblacion=["a", "b"], nivel=["A", "B"])
    escribir_tabla_sqlite(
        datos, db, "fact_cliente_score",
        ddl=esquema.ddl_de(datos, "fact_cliente_score"),
        indices=esquema.INDICES["fact_cliente_score"])
    con = sqlite3.connect(db)
    try:
        idx = [r[1] for r in con.execute('PRAGMA index_list("fact_cliente_score")')]
    finally:
        con.close()
    assert any("poblacion_nivel" in i for i in idx)


def test_ddl_de_devuelve_none_para_tablas_sin_reglas():
    assert esquema.ddl_de(_tabla(a=[1]), "tabla_inventada") is None
