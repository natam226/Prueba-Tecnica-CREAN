# Pipeline Analítico App de Inversiones CREAN — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible bronze→silver→gold pipeline over the 7 SQLite sources, produce a `cliente_features` table, train a propensity-to-adopt model, and export results for Power BI.

**Architecture:** Three SQLite databases (`bronce.db`, `plata.db`, `oro.db`), one per medallion layer, built by small Python scripts using pandas + sqlite3 (no PySpark — data volumes are ≤1M rows/table, well within pandas' comfort zone, and PySpark isn't installed in the venv; SPEC.md lists pandas/PySpark as alternatives, this picks pandas). Shared logic (zip/sqlite IO, time-series aggregation) lives in `src/` and is unit-tested. Notebooks consume the gold layer for EDA and modeling.

**Tech Stack:** Python, pandas, sqlite3, scikit-learn, matplotlib/seaborn, Jupyter, pytest, pyarrow.

## Global Constraints

- Etiqueta "adopción" = saldo activo (saldo_snapshot > 0) en Invesbot y/o Inversión Virtual.
- CDT y Fiducuenta son señal/predictor, nunca parte de la etiqueta.
- Capacidad de ahorro = ingresos_mensuales − total_egresos_mensuales.
- Cliente sin registro en una tabla de producto = saldo 0 / tenencia No.
- Clientes nulos en las 5 columnas financieras: conservar en `cliente_features` si tienen actividad en alguna tabla de producto (bandera `sin_dato_financiero`); excluir del modelado (`excluir_modelado`) solo si no tienen ninguna señal en ninguna fuente.
- Variables sensibles (`desc_genero`, `grupo_edad`, `desc_tipo_de_vivienda`) → solo caracterización descriptiva en EDA, nunca input del modelo de propensión.
- `bronce/` = ingesta cruda, sin transformar. `plata/` = una tabla por fuente a nivel cliente (o cliente-producto), con snapshot/prom_6m/tendencia. `oro/` = `cliente_features` ancha + esquema estrella liviano.
- `RANDOM_STATE = 42`, `TEST_SIZE = 0.2` for all train/test splits (implementation detail, not a business decision — documented here so every task uses the same values).

---

## Preguntas Abiertas (no resueltas por SPEC.md)

Estas son decisiones de modelado/negocio que SPEC.md no cubre. **No las resolví por mi cuenta.** Para que el plan siga siendo ejecutable, cada una lleva un valor **PROVISIONAL** claramente marcado en el código de las tareas afectadas — pero necesitan tu confirmación antes (o durante) de la ejecución del plan.

1. **Fecha de corte / ventana temporal.** Las fuentes con `fecha` no son diarias uniformes ni comparten rango: `crean_aho_cte` (2025-06-01 → 2026-06-07, 91 fechas distintas), `crean_bolsillos` (→ 2026-06-01, 37 fechas), `crean_fiducuenta` (→ 2026-06-06, 64 fechas), `crean_inv_virtual_cdt` (→ 2026-06-30, 391 fechas), `invesbot` (→ 2026-06-24, 389 fechas). SPEC.md no define una fecha de referencia global.
   **Provisional:** el snapshot ("último saldo") usa `MAX(fecha)` **por cliente-producto** (no ambiguo). Para "promedio 6M" y "tendencia", la ventana de 6 meses se cuenta hacia atrás desde `MAX(fecha)` **por fuente** (no por cliente). Ver Tarea 5.
2. **Definición de "tendencia".** SPEC.md la menciona pero no la define (¿pendiente de regresión?, ¿variación %?, ¿diferencia simple?).
   **Provisional:** `tendencia_6m = promedio(saldo en la 2ª mitad de la ventana de 6M) − promedio(saldo en la 1ª mitad)`. Ver Tarea 5.
3. **`estimador_ingreso` ausente (114.431 de 860.223 clientes no tienen fila en `estimador_ing.db`).** La regla "sin registro = saldo 0" de SPEC.md está pensada para tablas de saldo; `estimador_ingreso` no es un saldo, así que imponerle 0 sesgaría el dato.
   **Provisional:** se deja como `NULL` + bandera `tiene_estimador_ingreso`. Ver Tarea 13.
4. **Variable objetivo del modelo de "monto potencial a 12 meses".** SPEC.md pide el modelo pero no especifica qué cantidad exacta se predice (¿crecimiento proyectado de saldo Invesbot+Inversión Virtual?, ¿saldo total esperado?, ¿ticket de inversión?), ni hay 12 meses completos de histórico para todas las fuentes (los datos cubren ~13 meses en el mejor caso, y bastante menos en otras fuentes). **Esta tarea queda bloqueada (Tarea 21) hasta tener respuesta — no se implementa nada hasta entonces.**
5. **Definición operativa de "ninguna señal en ninguna fuente"** (regla de exclusión del modelado). Interpretación literal usada: el cliente no tiene ninguna fila en ninguna de las 6 fuentes de producto (`crean_aho_cte`, `crean_bolsillos`, `crean_fiducuenta`, `crean_inv_virtual_cdt`, `invesbot`, `estimador_ing`). Ver Tarea 14.
6. **[Añadida tras la revisión final] La etiqueta `etiqueta_adopcion` se mide en una fecha distinta por cliente, y para ~17% de los positivos esa fecha es antigua.** El snapshot usado para la etiqueta es `MAX(fecha)` por cliente-producto (Pregunta #1) — no ambiguo como *cálculo*, pero no es *consistente en el tiempo* entre clientes, y eso pesa mucho más para una etiqueta que para una feature. Medido sobre los datos reales: de los 60.324 snapshots positivos de `inversion_virtual`, 10.263 (17,0%) tienen fecha de snapshot anterior a la ventana de 6M, y 15.569 tienen más de 90 días de antigüedad frente al máximo de la fuente (2026-06-30); el más antiguo es de 2025-06-01, un año completo antes. Para `invesbot`, 222 de 5.214 positivos (4,3%) están fuera de la ventana. SPEC.md dice "saldo **activo**", que la mayoría interpretaría como *actualmente* activo — para ~17% de los positivos de inversión virtual, en realidad es "tenía saldo positivo la última vez que lo vimos, hace hasta un año". **No se resolvió unilateralmente** — requiere decidir si la etiqueta debe exigir que el snapshot esté dentro de una ventana reciente (y qué hacer con los clientes que quedarían sin poder evaluarse por falta de dato reciente).
7. **[Añadida tras la revisión final] La regla de exclusión del modelado (`excluir_modelado`) se aplicó a toda la población, no solo a los clientes con financieros nulos.** SPEC.md dice literalmente: *"Clientes nulos en las 5 columnas financieras: conservar... excluir del modelado **solo si** no tienen ninguna señal en ninguna fuente"* — la cláusula de exclusión está redactada específicamente para el subconjunto de clientes con datos financieros nulos. La implementación (Tarea 11) la aplica a los 860.223 clientes por igual. Medido: 90.548 clientes quedan excluidos, de los cuales solo 81 tienen `sin_dato_financiero=True` — es decir, **90.467 clientes con datos financieros completos fueron excluidos del modelado por una regla que, leída literalmente, apuntaba a otro subconjunto.** Son negativos garantizados (tasa de adopción exactamente 0 entre ellos), así que excluirlos del *entrenamiento* es razonable — pero también quedan sin score de propensión en el export final, y para un caso de uso de "a quién ofrecerle el producto", el segmento sin relación previa es justamente el más interesante de scorear. **No se resolvió unilateralmente** — requiere decidir si la exclusión debe limitarse a entrenamiento (y scorear igual a estos clientes en el export) o si de verdad se pretendía excluirlos también de cualquier score.

Hallazgos de calidad de datos que **no** son preguntas de negocio (decisiones técnicas de limpieza, resueltas directamente en el plan, documentadas para que quede constancia):
- `clientes.db` tiene 8 filas duplicadas exactas (mismo `numero_id`, mismos valores) → se deduplican en plata (Tarea 6).
- `crean_inv_virtual_cdt.db` tiene el valor de `producto` almacenado como `INVERSIóN VIRTUAL` (verificado a nivel de codepoint: U+0049...U+0053, U+00F3 ['ó' minúscula, no 'Ó'], U+004E...— UTF-8 perfectamente válido, **no** hay bytes corruptos). La anomalía real es de **casing**: todo el valor está en mayúsculas salvo la vocal acentuada, probablemente porque alguna conversión a mayúsculas upstream no manejó el caracter con tilde. Se normaliza por prefijo `INVERSI` (7 caracteres ASCII, siempre presentes) en vez de igualdad exacta, así que la normalización es indiferente a este detalle (Tarea 5/9).
- `sin_dato_financiero` se calculó con `.isnull().any(axis=1)` sobre las 5 columnas financieras (Tarea 6) — más conservador que `.all(axis=1)` (260 clientes vs. 249; las 4 columnas comparten 249 nulos, `total_patrimonio` tiene 11 nulos adicionales). SPEC.md dice "clientes nulos en las 5 columnas financieras", que en una lectura literal podría leerse como "nulos en las 5" (`all`). Se usó `any` por ser la interpretación más segura (conserva más señal), pero es una decisión de negocio implícita que no había quedado documentada hasta ahora.

---

## Estructura de Carpetas y Archivos

```
Prueba-Tecnica-CREAN/
├── SPEC.md
├── requirements.txt              # deps: pandas, numpy, scikit-learn, matplotlib, seaborn, jupyter, pyarrow, pytest
├── config.py                     # rutas de las 3 capas + constantes (ventana 6M, RANDOM_STATE, TEST_SIZE)
├── .gitignore                    # + bronce/data, plata/data, oro/data, outputs/, __pycache__, .ipynb_checkpoints
├── data/                         # zips originales (ya existen, sin tocar)
│   ├── clientes.zip
│   ├── crean_aho_cte.zip
│   ├── crean_bolsillos.zip
│   ├── crean_fiducuenta.zip
│   ├── crean_inv_virtual_cdt.zip
│   ├── invesbot.zip
│   └── estimador_ing.zip
├── src/
│   ├── __init__.py
│   ├── db_io.py                  # extraer_zip_a_db, leer_tabla_sqlite, escribir_tabla_sqlite
│   └── aggregations.py           # agregar_serie_saldo, normalizar_producto_inv_virtual
├── tests/
│   ├── test_db_io.py
│   └── test_aggregations.py
├── bronce/
│   ├── extraccion.py             # 7 fuentes → bronce.db, tablas sin transformar
│   ├── diagnostico_calidad.py    # nulos, duplicados, encoding, integridad referencial
│   └── data/
│       └── bronce.db             # generado (gitignored)
├── plata/
│   ├── transformacion.py         # limpieza clientes + agregación por fuente → plata.db
│   └── data/
│       └── plata.db              # generado (gitignored)
├── oro/
│   ├── construir_cliente_features.py   # join ancho, reglas de negocio, etiqueta, exclusión
│   ├── construir_esquema_estrella.py   # dim_cliente/producto/tiempo + fact_saldos
│   └── data/
│       └── oro.db                # generado (gitignored)
├── notebooks/
│   ├── 01_eda.ipynb
│   └── 02_modelado.ipynb
├── scripts/
│   └── export_powerbi.py         # oro.db → outputs/powerbi/*.csv
├── outputs/                      # generado (gitignored)
│   ├── quality/reporte_calidad.md
│   ├── eda/poblacion_modelado.csv
│   ├── models/propension_adopcion.pkl
│   └── powerbi/*.csv
└── docs/superpowers/plans/2026-08-05-pipeline-crean.md   # este documento
```

**Convenciones de nombres de tabla:**
- `bronce.db`: `clientes`, `crean_aho_cte`, `crean_bolsillos`, `crean_fiducuenta`, `crean_inv_virtual_cdt`, `invesbot`, `estimador_ing` (idénticos a los nombres reales dentro de cada `.db`).
- `plata.db`: `clientes_plata`, `aho_cte_plata`, `bolsillos_plata`, `fiducuenta_plata`, `cdt_inversion_virtual_plata`, `invesbot_plata`, `estimador_ingresos_plata` (grano cliente o cliente-producto, formato largo).
- `oro.db`: `cliente_features` (ancha, 1 fila/cliente), `dim_cliente`, `dim_producto`, `dim_tiempo`, `fact_saldos`.
- Slugs de producto canónicos (ASCII, sin acentos, para evitar el bug de encoding): `cuenta_ahorro`, `cuenta_corriente`, `bolsillos`, `fiducuenta`, `cdt`, `inversion_virtual`, `invesbot`.

---

## Task 1: Scaffold del proyecto

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Modify: `.gitignore`
- Create: `src/__init__.py`, `bronce/`, `plata/`, `oro/`, `notebooks/`, `scripts/`, `tests/`, `outputs/` (carpetas vacías, con `.gitkeep` donde haga falta)

**Interfaces:**
- Produces: `config.ROOT`, `config.DATA_DIR`, `config.BRONCE_DB`, `config.PLATA_DB`, `config.ORO_DB`, `config.OUTPUTS_DIR`, `config.VENTANA_MESES_AGREGACION`, `config.RANDOM_STATE`, `config.TEST_SIZE` — usados por todas las tareas siguientes.

- [ ] **Step 1: Crear `requirements.txt`**

```
pandas>=2.2
numpy>=1.26
scikit-learn>=1.4
matplotlib>=3.8
seaborn>=0.13
jupyter>=1.0
pyarrow>=15.0
pytest>=8.0
```

- [ ] **Step 2: Crear `config.py`**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
BRONCE_DIR = ROOT / "bronce" / "data"
PLATA_DIR = ROOT / "plata" / "data"
ORO_DIR = ROOT / "oro" / "data"
OUTPUTS_DIR = ROOT / "outputs"

BRONCE_DB = BRONCE_DIR / "bronce.db"
PLATA_DB = PLATA_DIR / "plata.db"
ORO_DB = ORO_DIR / "oro.db"

# --- Parámetros PROVISIONALES sujetos a confirmación (ver "Preguntas Abiertas" del plan) ---
VENTANA_MESES_AGREGACION = 6  # Pregunta Abierta #1 y #2
RANDOM_STATE = 42
TEST_SIZE = 0.2
```

- [ ] **Step 3: Crear carpetas y `.gitignore`**

```bash
mkdir -p src tests bronce/data plata/data oro/data notebooks scripts outputs/quality outputs/eda outputs/models outputs/powerbi
touch src/__init__.py
```

Añadir a `.gitignore` (mantener las líneas existentes `#venv` / `venv/`):

```
bronce/data/
plata/data/
oro/data/
outputs/
__pycache__/
*.pyc
.ipynb_checkpoints/
```

- [ ] **Step 4: Instalar dependencias**

El venv del proyecto (`venv/`, en la raíz del repo) ya trae `pandas`, `numpy` y `jupyter`, pero no `scikit-learn`, `pytest`, `pyarrow`, `matplotlib` ni `seaborn` — necesarios desde la Task 2 (pytest) en adelante. Instalar contra ese venv usando su ruta absoluta (funciona sin importar desde qué worktree/checkout se invoque):

Run (Windows): `"C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" -m pip install -r requirements.txt`
Expected: termina sin errores; instala/actualiza `scikit-learn`, `pytest`, `pyarrow`, `matplotlib`, `seaborn`.

- [ ] **Step 5: Verificar**

Run: `"C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" -c "import config; import pytest, sklearn, pyarrow, matplotlib, seaborn; print(config.BRONCE_DB, config.VENTANA_MESES_AGREGACION)"`
Expected: imprime la ruta de `bronce/data/bronce.db` y `6` sin errores de import.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.py .gitignore src/__init__.py
git commit -m "chore: scaffold project structure for medallion pipeline"
```

---

## Task 2: `src/db_io.py` — IO genérico zip/sqlite (TDD)

**Files:**
- Create: `tests/test_db_io.py`
- Create: `src/db_io.py`

**Interfaces:**
- Produces: `extraer_zip_a_db(zip_path: Path, destino_dir: Path) -> Path`, `leer_tabla_sqlite(db_path: Path, tabla: str) -> pd.DataFrame`, `escribir_tabla_sqlite(df: pd.DataFrame, db_path: Path, tabla: str, if_exists: str = "replace") -> None`. Usadas por `bronce/extraccion.py` (Task 3) y todos los scripts de `plata/`, `oro/`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_db_io.py
import sqlite3
import zipfile

import pandas as pd

from src.db_io import extraer_zip_a_db, leer_tabla_sqlite, escribir_tabla_sqlite


def test_extraer_zip_a_db(tmp_path):
    db_path = tmp_path / "origen.db"
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")

    zip_path = tmp_path / "origen.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.write(db_path, arcname="origen.db")

    destino = tmp_path / "extraido"
    resultado = extraer_zip_a_db(zip_path, destino)

    assert resultado == destino / "origen.db"
    assert resultado.exists()


def test_leer_y_escribir_tabla_sqlite(tmp_path):
    df = pd.DataFrame({"numero_id": [1, 2], "saldo": [10.0, 20.0]})
    db_path = tmp_path / "salida.db"

    escribir_tabla_sqlite(df, db_path, "mi_tabla")
    resultado = leer_tabla_sqlite(db_path, "mi_tabla")

    pd.testing.assert_frame_equal(resultado, df)
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_db_io.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.db_io'`

- [ ] **Step 3: Implementar `src/db_io.py`**

```python
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd


def extraer_zip_a_db(zip_path: Path, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        nombres_db = [n for n in z.namelist() if n.endswith(".db")]
        if len(nombres_db) != 1:
            raise ValueError(f"Se esperaba un único .db en {zip_path}, se encontraron {nombres_db}")
        z.extract(nombres_db[0], destino_dir)
    return destino_dir / nombres_db[0]


def leer_tabla_sqlite(db_path: Path, tabla: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql(f'SELECT * FROM "{tabla}"', con)


def escribir_tabla_sqlite(df: pd.DataFrame, db_path: Path, tabla: str, if_exists: str = "replace") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        df.to_sql(tabla, con, if_exists=if_exists, index=False)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_db_io.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/db_io.py tests/test_db_io.py
git commit -m "feat: add generic zip/sqlite IO helpers"
```

---

## Task 3: `bronce/extraccion.py` — ingesta cruda de las 7 fuentes

**Files:**
- Create: `bronce/extraccion.py`

**Interfaces:**
- Consumes: `src.db_io.extraer_zip_a_db`, `leer_tabla_sqlite`, `escribir_tabla_sqlite`; `config.DATA_DIR`, `config.BRONCE_DB`, `config.BRONCE_DIR`.
- Produces: `bronce/data/bronce.db` con 7 tablas idénticas a las fuentes (sin transformar). Consumido por `bronce/diagnostico_calidad.py` (Task 4) y todos los scripts de `plata/`.

- [ ] **Step 1: Escribir el script**

```python
# bronce/extraccion.py
from pathlib import Path

import config
from src.db_io import extraer_zip_a_db, leer_tabla_sqlite, escribir_tabla_sqlite

FUENTES = [
    ("clientes.zip", "clientes.db", "clientes"),
    ("crean_aho_cte.zip", "crean_aho_cte.db", "crean_aho_cte"),
    ("crean_bolsillos.zip", "crean_bolsillos.db", "crean_bolsillos"),
    ("crean_fiducuenta.zip", "crean_fiducuenta.db", "crean_fiducuenta"),
    ("crean_inv_virtual_cdt.zip", "crean_inv_virtual_cdt.db", "crean_inv_virtual_cdt"),
    ("invesbot.zip", "invesbot.db", "invesbot"),
    ("estimador_ing.zip", "estimador_ing.db", "estimador_ing"),
]


def main():
    staging = config.BRONCE_DIR / "_staging"
    for zip_name, db_filename, tabla in FUENTES:
        zip_path = config.DATA_DIR / zip_name
        db_path = extraer_zip_a_db(zip_path, staging)
        assert db_path.name == db_filename, f"esperaba {db_filename}, extraído {db_path.name}"
        df = leer_tabla_sqlite(db_path, tabla)
        escribir_tabla_sqlite(df, config.BRONCE_DB, tabla)
        print(f"{tabla}: {len(df)} filas -> bronce.db")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ejecutar**

Run: `python bronce/extraccion.py`
Expected: imprime 7 líneas, una por fuente, sin errores.

- [ ] **Step 3: Verificar conteos de filas**

Run:
```bash
python -c "
import sqlite3
import config
con = sqlite3.connect(config.BRONCE_DB)
esperado = {
    'clientes': 860231, 'crean_aho_cte': 1000000, 'crean_bolsillos': 1000000,
    'crean_fiducuenta': 1000000, 'crean_inv_virtual_cdt': 994177,
    'invesbot': 1000000, 'estimador_ing': 745792,
}
for tabla, n in esperado.items():
    c = con.execute(f'SELECT COUNT(*) FROM {tabla}').fetchone()[0]
    assert c == n, f'{tabla}: esperado {n}, obtenido {c}'
print('OK: 7/7 tablas con el conteo esperado')
"
```
Expected: `OK: 7/7 tablas con el conteo esperado`

- [ ] **Step 4: Commit**

```bash
git add bronce/extraccion.py
git commit -m "feat: extract 7 raw SQLite sources into bronce.db"
```

---

## Task 4: `bronce/diagnostico_calidad.py` — reporte de calidad (sin mutar datos)

**Files:**
- Create: `bronce/diagnostico_calidad.py`

**Interfaces:**
- Consumes: `config.BRONCE_DB`, `src.db_io.leer_tabla_sqlite`.
- Produces: `outputs/quality/reporte_calidad.md`. Documenta (no corrige) los hallazgos usados como base de las decisiones técnicas en `plata/transformacion.py` (Task 6+).

- [ ] **Step 1: Escribir el script**

```python
# bronce/diagnostico_calidad.py
import config
from src.db_io import leer_tabla_sqlite

TABLAS_SALDO = ["crean_aho_cte", "crean_bolsillos", "crean_fiducuenta", "crean_inv_virtual_cdt", "invesbot"]
COLS_FINANCIERAS = ["ingresos_mensuales", "total_egresos_mensuales", "total_activos", "total_pasivos", "total_patrimonio"]


def reporte_nulos_clientes(df):
    lineas = ["## Nulos en clientes"]
    for c in COLS_FINANCIERAS + ["desc_genero", "desc_tipo_de_vivienda"]:
        lineas.append(f"- {c}: {df[c].isnull().sum()} nulos")
    return lineas


def reporte_duplicados_clientes(df):
    dup = df["numero_id"].duplicated().sum()
    return [f"## Duplicados en clientes", f"- filas con numero_id repetido: {dup}"]


def reporte_encoding_producto(nombre_tabla, df):
    if "producto" not in df.columns:
        return []
    # No es corrupción de bytes (los valores son UTF-8 válido): se busca cualquier
    # caracter no-ASCII para detectar inconsistencias como "INVERSIóN VIRTUAL"
    # (ó minúscula en medio de un valor por lo demás en mayúsculas).
    sospechosos = df.loc[df["producto"].str.contains(r"[^\x00-\x7F]", na=False, regex=True), "producto"].unique().tolist()
    return [f"## Anomalías de texto en producto en {nombre_tabla}", f"- valores con caracteres no-ASCII: {sospechosos}"]


def reporte_integridad_referencial(nombre_tabla, df, ids_clientes):
    faltantes = set(df["numero_id"].unique()) - ids_clientes
    return [f"## Integridad referencial {nombre_tabla}", f"- numero_id sin match en clientes: {len(faltantes)}"]


def main():
    clientes = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    ids_clientes = set(clientes["numero_id"].unique())

    lineas = ["# Reporte de calidad — bronce", ""]
    lineas += reporte_nulos_clientes(clientes)
    lineas += reporte_duplicados_clientes(clientes)

    for tabla in TABLAS_SALDO:
        df = leer_tabla_sqlite(config.BRONCE_DB, tabla)
        lineas += reporte_encoding_producto(tabla, df)
        lineas += reporte_integridad_referencial(tabla, df, ids_clientes)

    estimador = leer_tabla_sqlite(config.BRONCE_DB, "estimador_ing")
    lineas += reporte_integridad_referencial("estimador_ing", estimador, ids_clientes)

    salida = config.OUTPUTS_DIR / "quality" / "reporte_calidad.md"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Reporte escrito en {salida}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ejecutar**

Run: `python bronce/diagnostico_calidad.py`
Expected: `Reporte escrito en outputs/quality/reporte_calidad.md`

- [ ] **Step 3: Verificar contenido esperado**

Run:
```bash
python -c "
import config
texto = (config.OUTPUTS_DIR / 'quality' / 'reporte_calidad.md').read_text(encoding='utf-8')
assert 'filas con numero_id repetido: 8' in texto
assert \"INVERSI\" in texto  # detecta el valor con la anomalía de texto (ó minúscula)
print('OK: reporte contiene los hallazgos esperados')
"
```
Expected: `OK: reporte contiene los hallazgos esperados`

- [ ] **Step 4: Commit**

```bash
git add bronce/diagnostico_calidad.py
git commit -m "feat: add bronze data quality diagnostics report"
```

---

## Task 5: `src/aggregations.py` — agregación de series y normalización de producto (TDD)

**Files:**
- Create: `tests/test_aggregations.py`
- Create: `src/aggregations.py`

**Interfaces:**
- Produces: `agregar_serie_saldo(df, group_cols, fecha_col="fecha", saldo_col="saldo", meses_ventana=6) -> pd.DataFrame` con columnas `group_cols + ["saldo_snapshot", "fecha_snapshot", "saldo_prom_6m", "tendencia_6m", "tenencia"]`; `normalizar_producto_inv_virtual(valor: str) -> str`. Usadas por `plata/transformacion.py` (Tasks 7-9).
- **Nota:** implementa el default PROVISIONAL de las Preguntas Abiertas #1 y #2. Si la respuesta cambia, solo esta función se modifica.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_aggregations.py
import pandas as pd

from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual


def test_agregar_serie_saldo_snapshot_es_el_mas_reciente():
    df = pd.DataFrame({
        "numero_id": [1, 1, 1],
        "fecha": ["2026-01-01", "2026-03-01", "2026-06-01"],
        "saldo": [100.0, 200.0, 300.0],
    })
    resultado = agregar_serie_saldo(df, group_cols=["numero_id"])
    fila = resultado.iloc[0]
    assert fila["saldo_snapshot"] == 300.0
    assert str(fila["fecha_snapshot"]) == "2026-06-01 00:00:00"


def test_agregar_serie_saldo_promedio_y_tendencia():
    # ventana de 6M hacia atrás desde 2026-06-01 => desde 2025-12-01
    df = pd.DataFrame({
        "numero_id": [1, 1, 1, 1],
        "fecha": ["2025-12-01", "2026-01-15", "2026-04-01", "2026-06-01"],
        "saldo": [100.0, 100.0, 300.0, 300.0],
    })
    resultado = agregar_serie_saldo(df, group_cols=["numero_id"])
    fila = resultado.iloc[0]
    assert fila["saldo_prom_6m"] == 200.0  # promedio de las 4 filas
    assert fila["tendencia_6m"] == 200.0  # promedio 2a mitad (300) - promedio 1a mitad (100)
    assert fila["tenencia"] == 1


def test_normalizar_producto_inv_virtual_corrige_casing_inconsistente():
    # Valor real en crean_inv_virtual_cdt.db: UTF-8 válido, pero con 'ó' minúscula
    # (U+00F3) en medio de un valor por lo demás en mayúsculas — no es corrupción
    # de bytes. El prefijo "INVERSI" (ASCII, siempre presente) es indiferente a esto.
    assert normalizar_producto_inv_virtual("INVERSIóN VIRTUAL") == "INVERSION_VIRTUAL"
    assert normalizar_producto_inv_virtual("CDT") == "CDT"
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_aggregations.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.aggregations'`

- [ ] **Step 3: Implementar `src/aggregations.py`**

```python
# src/aggregations.py
import pandas as pd


def agregar_serie_saldo(df, group_cols, fecha_col="fecha", saldo_col="saldo", meses_ventana=6):
    df = df.copy()
    df[fecha_col] = pd.to_datetime(df[fecha_col])
    fecha_corte = df[fecha_col].max()
    ventana_ini = fecha_corte - pd.DateOffset(months=meses_ventana)
    mitad = fecha_corte - pd.DateOffset(months=meses_ventana // 2)

    snapshot = (
        df.sort_values(fecha_col)
        .groupby(group_cols, as_index=False)
        .agg(saldo_snapshot=(saldo_col, "last"), fecha_snapshot=(fecha_col, "last"))
    )

    ventana = df[df[fecha_col] >= ventana_ini]
    prom6m = (
        ventana.groupby(group_cols, as_index=False)[saldo_col]
        .mean()
        .rename(columns={saldo_col: "saldo_prom_6m"})
    )

    primera_mitad = ventana[ventana[fecha_col] < mitad].groupby(group_cols)[saldo_col].mean()
    segunda_mitad = ventana[ventana[fecha_col] >= mitad].groupby(group_cols)[saldo_col].mean()
    tendencia = (segunda_mitad - primera_mitad).rename("tendencia_6m").reset_index()

    out = snapshot.merge(prom6m, on=group_cols, how="left").merge(tendencia, on=group_cols, how="left")
    out["tendencia_6m"] = out["tendencia_6m"].fillna(0.0)
    out["tenencia"] = 1
    return out


def normalizar_producto_inv_virtual(valor: str) -> str:
    if valor == "CDT":
        return "CDT"
    if str(valor).startswith("INVERSI"):
        return "INVERSION_VIRTUAL"
    return valor
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_aggregations.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/aggregations.py tests/test_aggregations.py
git commit -m "feat: add time-series aggregation and producto normalization helpers"
```

---

## Task 6: `plata/transformacion.py` — limpieza de `clientes`

**Files:**
- Create: `plata/transformacion.py`

**Interfaces:**
- Consumes: `config.BRONCE_DB`, `config.PLATA_DB`, `src.db_io.leer_tabla_sqlite`, `escribir_tabla_sqlite`.
- Produces: tabla `clientes_plata` en `plata.db` con columnas: `numero_id, grupo_edad, desc_genero, desc_segmento, desc_tipo_de_vivienda, ingresos_mensuales, total_egresos_mensuales, total_activos, total_pasivos, total_patrimonio, capacidad_ahorro, sin_dato_financiero`. Consumida por `oro/construir_cliente_features.py` (Task 11).

- [ ] **Step 1: Escribir la función de limpieza**

```python
# plata/transformacion.py
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

COLS_FINANCIERAS = ["ingresos_mensuales", "total_egresos_mensuales", "total_activos", "total_pasivos", "total_patrimonio"]


def limpiar_clientes():
    df = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    df = df.drop_duplicates(subset="numero_id", keep="first")
    df["sin_dato_financiero"] = df[COLS_FINANCIERAS].isnull().any(axis=1)
    df["capacidad_ahorro"] = df["ingresos_mensuales"] - df["total_egresos_mensuales"]
    escribir_tabla_sqlite(df, config.PLATA_DB, "clientes_plata")
    return df


if __name__ == "__main__":
    df = limpiar_clientes()
    print(f"clientes_plata: {len(df)} filas, {df['sin_dato_financiero'].sum()} con sin_dato_financiero")
```

- [ ] **Step 2: Ejecutar**

Run: `python -m plata.transformacion`
Expected: `clientes_plata: 860223 filas, 260 con sin_dato_financiero`

- [ ] **Step 3: Verificar sin duplicados y tipo de `capacidad_ahorro`**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.PLATA_DB, 'clientes_plata')
assert df['numero_id'].is_unique
assert df['capacidad_ahorro'].dtype.kind == 'f'
print('OK: clientes_plata sin duplicados y capacidad_ahorro numérica')
"
```
Expected: `OK: clientes_plata sin duplicados y capacidad_ahorro numérica`

- [ ] **Step 4: Commit**

```bash
git add plata/transformacion.py
git commit -m "feat: build clientes_plata with dedup, sin_dato_financiero and capacidad_ahorro"
```

---

## Task 7: `plata/transformacion.py` — `crean_aho_cte` → `aho_cte_plata`

**Files:**
- Modify: `plata/transformacion.py`

**Interfaces:**
- Consumes: `src.aggregations.agregar_serie_saldo`.
- Produces: tabla `aho_cte_plata` en `plata.db`, grano cliente-producto, columnas: `numero_id, producto, saldo_snapshot, fecha_snapshot, saldo_prom_6m, tendencia_6m, tenencia`, con `producto ∈ {cuenta_ahorro, cuenta_corriente}`.

- [ ] **Step 1: Añadir la función**

```python
# plata/transformacion.py (añadir al final, junto a los imports existentes)
from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual

MAPA_PRODUCTO_SLUG = {
    "CUENTA DE AHORRO": "cuenta_ahorro",
    "CUENTA DE CORRIENTE": "cuenta_corriente",
    "BOLSILLOS": "bolsillos",
    "FIDUCUENTA": "fiducuenta",
    "CDT": "cdt",
    "INVERSION_VIRTUAL": "inversion_virtual",
    "INVESBOT": "invesbot",
}


def transformar_aho_cte():
    df = leer_tabla_sqlite(config.BRONCE_DB, "crean_aho_cte")
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(df, group_cols=["numero_id", "producto"], meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "aho_cte_plata")
    return resultado
```

- [ ] **Step 2: Añadir la llamada al bloque `__main__`**

```python
if __name__ == "__main__":
    df = limpiar_clientes()
    print(f"clientes_plata: {len(df)} filas, {df['sin_dato_financiero'].sum()} con sin_dato_financiero")
    aho = transformar_aho_cte()
    print(f"aho_cte_plata: {len(aho)} filas, productos={sorted(aho['producto'].unique())}")
```

- [ ] **Step 3: Ejecutar**

Run: `python -m plata.transformacion`
Expected: última línea `aho_cte_plata: <N> filas, productos=['cuenta_ahorro', 'cuenta_corriente']`

- [ ] **Step 4: Verificar**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.PLATA_DB, 'aho_cte_plata')
assert set(df['producto'].unique()) == {'cuenta_ahorro', 'cuenta_corriente'}
assert not df.duplicated(subset=['numero_id', 'producto']).any()
print('OK: aho_cte_plata con productos correctos y sin duplicados cliente-producto')
"
```
Expected: `OK: aho_cte_plata con productos correctos y sin duplicados cliente-producto`

- [ ] **Step 5: Commit**

```bash
git add plata/transformacion.py
git commit -m "feat: build aho_cte_plata split by cuenta_ahorro/cuenta_corriente"
```

---

## Task 8: `plata/transformacion.py` — bolsillos/fiducuenta/invesbot → plata (fuentes de producto único)

Estas 3 fuentes comparten exactamente la misma lógica de transformación (una tabla con `fecha, numero_id, producto, saldo`, un único valor de `producto`), así que se implementan como un único bucle parametrizado en vez de 3 funciones casi idénticas.

**Files:**
- Modify: `plata/transformacion.py`

**Interfaces:**
- Produces: tablas `bolsillos_plata`, `fiducuenta_plata`, `invesbot_plata` en `plata.db`, mismas columnas que Task 7 (`numero_id, producto, saldo_snapshot, fecha_snapshot, saldo_prom_6m, tendencia_6m, tenencia`), con `producto` fijo por tabla (`bolsillos`, `fiducuenta`, `invesbot` respectivamente).

- [ ] **Step 1: Añadir la función y la tabla de fuentes**

```python
FUENTES_PRODUCTO_UNICO = [
    ("crean_bolsillos", "bolsillos_plata"),
    ("crean_fiducuenta", "fiducuenta_plata"),
    ("invesbot", "invesbot_plata"),
]


def transformar_producto_unico(tabla_bronce, tabla_plata_destino):
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(df, group_cols=["numero_id", "producto"], meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, tabla_plata_destino)
    return resultado
```

- [ ] **Step 2: Añadir el bucle al bloque `__main__`**

```python
    for tabla_bronce, tabla_plata_destino in FUENTES_PRODUCTO_UNICO:
        resultado = transformar_producto_unico(tabla_bronce, tabla_plata_destino)
        print(f"{tabla_plata_destino}: {len(resultado)} filas")
```

- [ ] **Step 3: Ejecutar**

Run: `python -m plata.transformacion`
Expected: 3 líneas nuevas — `bolsillos_plata: 260714 filas`, `fiducuenta_plata: 181021 filas`, `invesbot_plata: 5214 filas`

- [ ] **Step 4: Verificar**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
esperado = {'bolsillos_plata': ('bolsillos', 260714), 'fiducuenta_plata': ('fiducuenta', 181021), 'invesbot_plata': ('invesbot', 5214)}
for tabla, (producto, n) in esperado.items():
    df = leer_tabla_sqlite(config.PLATA_DB, tabla)
    assert (df['producto'] == producto).all(), tabla
    assert len(df) == n, f'{tabla}: esperado {n}, obtenido {len(df)}'
print('OK: bolsillos_plata, fiducuenta_plata, invesbot_plata')
"
```
Expected: `OK: bolsillos_plata, fiducuenta_plata, invesbot_plata`

- [ ] **Step 5: Commit**

```bash
git add plata/transformacion.py
git commit -m "feat: build bolsillos_plata, fiducuenta_plata, invesbot_plata via shared loop"
```

---

## Task 9: `plata/transformacion.py` — `crean_inv_virtual_cdt` → `cdt_inversion_virtual_plata`

**Files:**
- Modify: `plata/transformacion.py`

**Interfaces:**
- Consumes: `normalizar_producto_inv_virtual` (corrige la inconsistencia de casing — 'ó' minúscula en "INVERSIóN VIRTUAL" — antes de mapear a slug; el dato es UTF-8 válido, no hay corrupción de bytes).
- Produces: tabla `cdt_inversion_virtual_plata` en `plata.db`, `producto ∈ {cdt, inversion_virtual}`.

- [ ] **Step 1: Añadir la función**

```python
def transformar_cdt_inversion_virtual():
    df = leer_tabla_sqlite(config.BRONCE_DB, "crean_inv_virtual_cdt")
    df["producto"] = df["producto"].apply(normalizar_producto_inv_virtual).map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(df, group_cols=["numero_id", "producto"], meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "cdt_inversion_virtual_plata")
    return resultado
```

- [ ] **Step 2: Añadir al bloque `__main__`**

```python
    cdt_iv = transformar_cdt_inversion_virtual()
    print(f"cdt_inversion_virtual_plata: {len(cdt_iv)} filas, productos={sorted(cdt_iv['producto'].unique())}")
```

- [ ] **Step 3: Ejecutar**

Run: `python -m plata.transformacion`
Expected: última línea `cdt_inversion_virtual_plata: <N> filas, productos=['cdt', 'inversion_virtual']`

- [ ] **Step 4: Verificar (confirma que la normalización de casing funcionó)**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.PLATA_DB, 'cdt_inversion_virtual_plata')
assert set(df['producto'].unique()) == {'cdt', 'inversion_virtual'}
assert df['producto'].isnull().sum() == 0  # ningún valor quedó sin mapear por la inconsistencia de casing
print('OK: cdt_inversion_virtual_plata sin productos sin mapear')
"
```
Expected: `OK: cdt_inversion_virtual_plata sin productos sin mapear`

- [ ] **Step 5: Commit**

```bash
git add plata/transformacion.py
git commit -m "feat: build cdt_inversion_virtual_plata with casing normalization for producto"
```

---

## Task 10: `plata/transformacion.py` — `estimador_ing` → `estimador_ingresos_plata`

**Files:**
- Modify: `plata/transformacion.py`

**Interfaces:**
- Produces: tabla `estimador_ingresos_plata` en `plata.db`, columnas: `numero_id, estimador_ingreso, tiene_estimador_ingreso`. No tiene `fecha`, así que no pasa por `agregar_serie_saldo`. Implementa la Pregunta Abierta #3 (no imputa, deja `NULL` cuando falta).

- [ ] **Step 1: Añadir la función**

```python
def transformar_estimador_ingresos():
    df = leer_tabla_sqlite(config.BRONCE_DB, "estimador_ing")[["numero_id", "estimador_ingreso"]]
    df["tiene_estimador_ingreso"] = True
    escribir_tabla_sqlite(df, config.PLATA_DB, "estimador_ingresos_plata")
    return df
```

- [ ] **Step 2: Añadir al bloque `__main__`**

```python
    est = transformar_estimador_ingresos()
    print(f"estimador_ingresos_plata: {len(est)} filas")
```

- [ ] **Step 3: Ejecutar**

Run: `python -m plata.transformacion`
Expected: última línea `estimador_ingresos_plata: 745792 filas`

- [ ] **Step 4: Verificar**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.PLATA_DB, 'estimador_ingresos_plata')
assert df['numero_id'].is_unique
assert df['tiene_estimador_ingreso'].all()
print('OK: estimador_ingresos_plata')
"
```
Expected: `OK: estimador_ingresos_plata`

- [ ] **Step 5: Commit**

```bash
git add plata/transformacion.py
git commit -m "feat: build estimador_ingresos_plata (no imputation, NULL preserved)"
```

---

## Task 11: `oro/construir_cliente_features.py` — join ancho + reglas de negocio

**Files:**
- Create: `oro/construir_cliente_features.py`

**Interfaces:**
- Consumes: las 7 tablas de `plata.db` (Tasks 6-10).
- Produces: tabla `cliente_features` en `oro.db`, 1 fila/cliente (860.223 filas), con columnas demográficas, `capacidad_ahorro`, `sin_dato_financiero`, por cada uno de los 7 productos (`cuenta_ahorro, cuenta_corriente, bolsillos, fiducuenta, cdt, inversion_virtual, invesbot`): `{producto}_saldo_snapshot, {producto}_saldo_prom_6m, {producto}_tendencia_6m, {producto}_tenencia`; más `estimador_ingreso, tiene_estimador_ingreso, etiqueta_adopcion, excluir_modelado`. Consumida por `oro/construir_esquema_estrella.py` (Task 12), notebooks de EDA/modelado (Tasks 13-17), y `scripts/export_powerbi.py` (Task 19).

- [ ] **Step 1: Escribir el script**

```python
# oro/construir_cliente_features.py
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

PRODUCTOS = ["cuenta_ahorro", "cuenta_corriente", "bolsillos", "fiducuenta", "cdt", "inversion_virtual", "invesbot"]

TABLAS_PRODUCTO = {
    "cuenta_ahorro": "aho_cte_plata",
    "cuenta_corriente": "aho_cte_plata",
    "bolsillos": "bolsillos_plata",
    "fiducuenta": "fiducuenta_plata",
    "cdt": "cdt_inversion_virtual_plata",
    "inversion_virtual": "cdt_inversion_virtual_plata",
    "invesbot": "invesbot_plata",
}


def _pivotear_producto(clientes_ids, producto):
    tabla = TABLAS_PRODUCTO[producto]
    df = leer_tabla_sqlite(config.PLATA_DB, tabla)
    df = df[df["producto"] == producto].drop(columns=["producto", "fecha_snapshot"])
    df = df.rename(columns={
        "saldo_snapshot": f"{producto}_saldo_snapshot",
        "saldo_prom_6m": f"{producto}_saldo_prom_6m",
        "tendencia_6m": f"{producto}_tendencia_6m",
        "tenencia": f"{producto}_tenencia",
    })
    return df


def construir_cliente_features():
    base = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")

    for producto in PRODUCTOS:
        df_producto = _pivotear_producto(base["numero_id"], producto)
        base = base.merge(df_producto, on="numero_id", how="left")
        base[f"{producto}_saldo_snapshot"] = base[f"{producto}_saldo_snapshot"].fillna(0.0)
        base[f"{producto}_saldo_prom_6m"] = base[f"{producto}_saldo_prom_6m"].fillna(0.0)
        base[f"{producto}_tendencia_6m"] = base[f"{producto}_tendencia_6m"].fillna(0.0)
        base[f"{producto}_tenencia"] = base[f"{producto}_tenencia"].fillna(0).astype(int)

    estimador = leer_tabla_sqlite(config.PLATA_DB, "estimador_ingresos_plata")
    base = base.merge(estimador, on="numero_id", how="left")
    # fillna ANTES de astype(bool): tras el merge la columna queda en dtype object
    # (mezcla de bool True y NaN); castear antes de fillna dejaría NaN -> True.
    base["tiene_estimador_ingreso"] = base["tiene_estimador_ingreso"].fillna(False).astype(bool)

    base["etiqueta_adopcion"] = (
        (base["invesbot_saldo_snapshot"] > 0) | (base["inversion_virtual_saldo_snapshot"] > 0)
    ).astype(int)

    tenencia_cols = [f"{p}_tenencia" for p in PRODUCTOS]
    base["excluir_modelado"] = (
        (base[tenencia_cols].sum(axis=1) == 0) & (~base["tiene_estimador_ingreso"])
    ).astype(int)

    escribir_tabla_sqlite(base, config.ORO_DB, "cliente_features")
    return base


if __name__ == "__main__":
    df = construir_cliente_features()
    print(f"cliente_features: {len(df)} filas, {df.shape[1]} columnas")
    print(f"tasa adopción: {df['etiqueta_adopcion'].mean():.4f}")
    print(f"excluidos del modelado: {df['excluir_modelado'].sum()}")
```

- [ ] **Step 2: Ejecutar**

Run: `python -m oro.construir_cliente_features`
Expected: `cliente_features: 860223 filas, 44 columnas` (12 de `clientes_plata` [10 originales + `sin_dato_financiero` + `capacidad_ahorro`] + 7 productos × 4 cols = 28 + 2 de estimador + 2 de etiqueta/exclusión = 44; el conteo de **filas** es el chequeo exacto — si el de columnas difiere ligeramente por una decisión de implementación, no es bloqueante)

- [ ] **Step 3: Verificar shape, nulos y sanity check de la etiqueta**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
assert len(df) == 860223
assert df['numero_id'].is_unique
assert df['etiqueta_adopcion'].isin([0, 1]).all()
# cota superior conocida: invesbot tiene a lo sumo 5214 ids, inversion_virtual es un subconjunto de los 84104 ids de cdt_inv_virtual
assert df['etiqueta_adopcion'].sum() <= 5214 + 84104
assert df['excluir_modelado'].isin([0, 1]).all()
print('OK: cliente_features con shape, unicidad y etiqueta dentro de cotas esperadas')
"
```
Expected: `OK: cliente_features con shape, unicidad y etiqueta dentro de cotas esperadas`

- [ ] **Step 4: Commit**

```bash
git add oro/construir_cliente_features.py
git commit -m "feat: build cliente_features gold table with adoption label and exclusion flag"
```

---

## Task 12: `oro/construir_esquema_estrella.py` — esquema estrella liviano para el tablero

**Files:**
- Create: `oro/construir_esquema_estrella.py`

**Interfaces:**
- Consumes: las 5 tablas producto de `plata.db` (Tasks 7-9) + `clientes_plata` (Task 6).
- Produces: `dim_cliente, dim_producto, dim_tiempo, fact_saldos` en `oro.db`. `fact_saldos` a grano cliente-producto (snapshot), no serie diaria completa — "liviano" según SPEC.md.

- [ ] **Step 1: Escribir el script**

```python
# oro/construir_esquema_estrella.py
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

TABLAS_PRODUCTO_LARGAS = [
    "aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
    "cdt_inversion_virtual_plata", "invesbot_plata",
]


def construir_esquema_estrella():
    clientes = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")
    dim_cliente = clientes[["numero_id", "grupo_edad", "desc_genero", "desc_segmento", "desc_tipo_de_vivienda"]]
    escribir_tabla_sqlite(dim_cliente, config.ORO_DB, "dim_cliente")

    fact_frames = [leer_tabla_sqlite(config.PLATA_DB, t) for t in TABLAS_PRODUCTO_LARGAS]
    fact_saldos = pd.concat(fact_frames, ignore_index=True)

    dim_producto = pd.DataFrame({"producto": sorted(fact_saldos["producto"].unique())})
    dim_producto["producto_id"] = range(1, len(dim_producto) + 1)
    escribir_tabla_sqlite(dim_producto, config.ORO_DB, "dim_producto")

    fact_saldos["fecha_snapshot"] = pd.to_datetime(fact_saldos["fecha_snapshot"])
    dim_tiempo = fact_saldos[["fecha_snapshot"]].drop_duplicates().rename(columns={"fecha_snapshot": "fecha"})
    dim_tiempo["anio"] = dim_tiempo["fecha"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha"].dt.month
    dim_tiempo["trimestre"] = dim_tiempo["fecha"].dt.quarter
    escribir_tabla_sqlite(dim_tiempo, config.ORO_DB, "dim_tiempo")

    fact_saldos = fact_saldos.merge(dim_producto, on="producto", how="left")
    escribir_tabla_sqlite(fact_saldos, config.ORO_DB, "fact_saldos")
    return dim_cliente, dim_producto, dim_tiempo, fact_saldos


if __name__ == "__main__":
    dim_cliente, dim_producto, dim_tiempo, fact_saldos = construir_esquema_estrella()
    print(f"dim_cliente: {len(dim_cliente)}, dim_producto: {len(dim_producto)}, "
          f"dim_tiempo: {len(dim_tiempo)}, fact_saldos: {len(fact_saldos)}")
```

- [ ] **Step 2: Ejecutar**

Run: `python -m oro.construir_esquema_estrella`
Expected: imprime los 4 conteos sin errores; `dim_producto` debe tener 7 filas.

- [ ] **Step 3: Verificar integridad del esquema estrella**

Run:
```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
fact = leer_tabla_sqlite(config.ORO_DB, 'fact_saldos')
dim_p = leer_tabla_sqlite(config.ORO_DB, 'dim_producto')
dim_c = leer_tabla_sqlite(config.ORO_DB, 'dim_cliente')
assert len(dim_p) == 7
assert fact['producto_id'].isnull().sum() == 0
assert set(fact['numero_id'].unique()) <= set(dim_c['numero_id'].unique())
print('OK: esquema estrella íntegro')
"
```
Expected: `OK: esquema estrella íntegro`

- [ ] **Step 4: Commit**

```bash
git add oro/construir_esquema_estrella.py
git commit -m "feat: build lightweight star schema for Power BI dashboard"
```

---

## Task 13: Notebook EDA — carga y resumen de nulos/shape

**Files:**
- Create: `notebooks/01_eda.ipynb`

**Interfaces:**
- Consumes: `cliente_features` de `oro.db` (Task 11).
- Produces: `outputs/eda/resumen_shape.json` (marcador verificable sin abrir el notebook).

- [ ] **Step 1: Crear el notebook con una celda de código**

En Jupyter, crear `notebooks/01_eda.ipynb` y añadir esta celda:

```python
import json
import sys
sys.path.insert(0, "..")

import pandas as pd
import config
from src.db_io import leer_tabla_sqlite

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
resumen = {
    "n_filas": len(df),
    "n_columnas": df.shape[1],
    "nulos_por_columna": df.isnull().sum().to_dict(),
}
(config.OUTPUTS_DIR / "eda").mkdir(parents=True, exist_ok=True)
with open(config.OUTPUTS_DIR / "eda" / "resumen_shape.json", "w") as f:
    json.dump({k: v for k, v in resumen.items() if k != "nulos_por_columna"} |
              {"nulos_por_columna": {k: int(v) for k, v in resumen["nulos_por_columna"].items()}}, f, indent=2)
df.describe(include="all").T
```

- [ ] **Step 2: Ejecutar el notebook**

Run: `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb`
Expected: termina sin error (exit code 0).

- [ ] **Step 3: Verificar el marcador de salida**

Run:
```bash
python -c "
import json
import config
with open(config.OUTPUTS_DIR / 'eda' / 'resumen_shape.json') as f:
    r = json.load(f)
assert r['n_filas'] == 860223
print('OK: resumen_shape.json con el conteo de filas esperado')
"
```
Expected: `OK: resumen_shape.json con el conteo de filas esperado`

- [ ] **Step 4: Commit**

```bash
git add notebooks/01_eda.ipynb
git commit -m "feat: add EDA notebook load/summary cell"
```

---

## Task 14: Notebook EDA — variables sensibles, solo caracterización descriptiva

**Files:**
- Modify: `notebooks/01_eda.ipynb`

**Interfaces:**
- Produces: gráficos inline + `outputs/eda/tasas_adopcion_por_segmento.csv`. **Estas variables no deben usarse como input del modelo (Task 17 las excluye explícitamente).**

- [ ] **Step 1: Añadir una celda de código**

```python
import matplotlib.pyplot as plt

sensibles = ["grupo_edad", "desc_genero", "desc_segmento", "desc_tipo_de_vivienda"]
tablas = []
for col in sensibles:
    t = df.groupby(col, dropna=False)["etiqueta_adopcion"].agg(["mean", "count"]).reset_index()
    t.insert(0, "variable", col)
    t = t.rename(columns={col: "categoria", "mean": "tasa_adopcion", "count": "n_clientes"})
    tablas.append(t)

resumen_sensibles = pd.concat(tablas, ignore_index=True)
resumen_sensibles.to_csv(config.OUTPUTS_DIR / "eda" / "tasas_adopcion_por_segmento.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for ax, col in zip(axes.flat, sensibles):
    subset = resumen_sensibles[resumen_sensibles["variable"] == col]
    ax.bar(subset["categoria"].astype(str), subset["tasa_adopcion"])
    ax.set_title(col)
    ax.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(config.OUTPUTS_DIR / "eda" / "tasas_adopcion_por_segmento.png")

resumen_sensibles
```

- [ ] **Step 2: Ejecutar el notebook**

Run: `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb`
Expected: exit code 0.

- [ ] **Step 3: Verificar**

Run:
```bash
python -c "
import pandas as pd
import config
t = pd.read_csv(config.OUTPUTS_DIR / 'eda' / 'tasas_adopcion_por_segmento.csv')
assert set(t['variable'].unique()) == {'grupo_edad', 'desc_genero', 'desc_segmento', 'desc_tipo_de_vivienda'}
assert t['tasa_adopcion'].between(0, 1).all()
assert (config.OUTPUTS_DIR / 'eda' / 'tasas_adopcion_por_segmento.png').exists()
print('OK: tasas de adopción por variable sensible calculadas, gráfico generado')
"
```
Expected: `OK: tasas de adopción por variable sensible calculadas`

- [ ] **Step 4: Commit**

```bash
git add notebooks/01_eda.ipynb
git commit -m "feat: add descriptive-only breakdown of adoption by sensitive variables"
```

---

## Task 15: Notebook EDA — señal financiera/producto y población de modelado

**Files:**
- Modify: `notebooks/01_eda.ipynb`

**Interfaces:**
- Produces: `outputs/eda/poblacion_modelado.csv` (lista de `numero_id` con `excluir_modelado == 0`), consumida por Task 17.

- [ ] **Step 1: Añadir una celda de código**

```python
saldo_cols = [c for c in df.columns if c.endswith("_saldo_snapshot")]
resumen_saldos = df.groupby("etiqueta_adopcion")[saldo_cols + ["capacidad_ahorro"]].mean()
print(resumen_saldos)

poblacion_modelado = df.loc[df["excluir_modelado"] == 0, ["numero_id"]]
poblacion_modelado.to_csv(config.OUTPUTS_DIR / "eda" / "poblacion_modelado.csv", index=False)
print(f"población de modelado: {len(poblacion_modelado)} de {len(df)} clientes")
```

- [ ] **Step 2: Ejecutar el notebook**

Run: `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb`
Expected: exit code 0.

- [ ] **Step 3: Verificar**

Run:
```bash
python -c "
import pandas as pd
import config
pop = pd.read_csv(config.OUTPUTS_DIR / 'eda' / 'poblacion_modelado.csv')
assert pop['numero_id'].is_unique
assert len(pop) < 860223
print(f'OK: población de modelado = {len(pop)} clientes')
"
```
Expected: `OK: población de modelado = <N> clientes` (con `N < 860223`)

- [ ] **Step 4: Commit**

```bash
git add notebooks/01_eda.ipynb
git commit -m "feat: compute EDA financial signal summary and modeling population"
```

---

## Task 16: Notebook modelado — dataset de modelado sin fuga de información

**Files:**
- Create: `notebooks/02_modelado.ipynb`

**Interfaces:**
- Consumes: `cliente_features` (oro), `outputs/eda/poblacion_modelado.csv` (Task 15).
- Produces: `X_train, X_test, y_train, y_test` en el kernel del notebook, usados por Task 17.
- **Nota crítica de fuga de datos:** `invesbot_*` e `inversion_virtual_*` no pueden ser features (definen la etiqueta). `desc_genero`, `grupo_edad`, `desc_tipo_de_vivienda` no pueden ser features (variables sensibles, Global Constraints).

- [ ] **Step 1: Crear el notebook con una celda de código**

```python
import sys
sys.path.insert(0, "..")

import pandas as pd
from sklearn.model_selection import train_test_split

import config
from src.db_io import leer_tabla_sqlite

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
poblacion = pd.read_csv(config.OUTPUTS_DIR / "eda" / "poblacion_modelado.csv")
df = df[df["numero_id"].isin(poblacion["numero_id"])].reset_index(drop=True)

COLUMNAS_SENSIBLES = ["desc_genero", "grupo_edad", "desc_tipo_de_vivienda"]
COLUMNAS_FUGA = [c for c in df.columns if c.startswith("invesbot_") or c.startswith("inversion_virtual_")]
COLUMNAS_NO_FEATURE = ["numero_id", "etiqueta_adopcion", "excluir_modelado"] + COLUMNAS_SENSIBLES + COLUMNAS_FUGA

feature_cols = [c for c in df.columns if c not in COLUMNAS_NO_FEATURE]
X = pd.get_dummies(df[feature_cols], columns=["desc_segmento"], drop_first=True)
X = X.fillna({"estimador_ingreso": X["estimador_ingreso"].median()})
y = df["etiqueta_adopcion"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=config.TEST_SIZE, random_state=config.RANDOM_STATE, stratify=y
)
print(f"train: {X_train.shape}, test: {X_test.shape}, tasa adopción train: {y_train.mean():.4f}")
```

- [ ] **Step 2: Ejecutar el notebook**

Run: `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_modelado.ipynb`
Expected: exit code 0.

- [ ] **Step 3: Verificar que no hay fuga de datos ni variables sensibles**

Añadir y ejecutar una celda de verificación:

```python
assert not any(c.startswith("invesbot_") or c.startswith("inversion_virtual_") for c in X.columns)
assert not any(c in X.columns for c in COLUMNAS_SENSIBLES)
print("OK: sin fuga de datos ni variables sensibles en las features")
```

Expected: `OK: sin fuga de datos ni variables sensibles en las features`

- [ ] **Step 4: Commit**

```bash
git add notebooks/02_modelado.ipynb
git commit -m "feat: build leakage-free, non-sensitive modeling dataset"
```

---

## Task 17: Notebook modelado — modelo de propensión a adopción

**Files:**
- Modify: `notebooks/02_modelado.ipynb`

**Interfaces:**
- Consumes: `X_train, X_test, y_train, y_test` (Task 16).
- Produces: `outputs/models/propension_adopcion.pkl`, `outputs/models/metricas_propension.json`.

- [ ] **Step 1: Añadir una celda de código**

```python
import json
import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score

# Task 16 solo imputa estimador_ingreso. ~179 clientes en la población de
# modelado (de los ~260 sin_dato_financiero) siguen con NaN reales en
# ingresos_mensuales/total_egresos_mensuales/total_activos/total_pasivos/
# total_patrimonio/capacidad_ahorro — GradientBoostingClassifier no acepta
# NaN. Se imputa con la media de TRAIN (nunca de test, para no filtrar
# estadísticas de test hacia el entrenamiento).
X_train_filled = X_train.fillna(X_train.mean())
X_test_filled = X_test.fillna(X_train.mean())

modelo = GradientBoostingClassifier(random_state=config.RANDOM_STATE)
modelo.fit(X_train_filled, y_train)

proba = modelo.predict_proba(X_test_filled)[:, 1]
pred = modelo.predict(X_test_filled)

metricas = {
    "auc": roc_auc_score(y_test, proba),
    "precision": precision_score(y_test, pred),
    "recall": recall_score(y_test, pred),
}
print(metricas)

(config.OUTPUTS_DIR / "models").mkdir(parents=True, exist_ok=True)
joblib.dump(modelo, config.OUTPUTS_DIR / "models" / "propension_adopcion.pkl")
with open(config.OUTPUTS_DIR / "models" / "metricas_propension.json", "w") as f:
    json.dump(metricas, f, indent=2)
```

- [ ] **Step 2: Ejecutar el notebook**

Run: `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_modelado.ipynb`
Expected: exit code 0, imprime un dict con `auc`, `precision`, `recall`.

- [ ] **Step 3: Verificar**

Run:
```bash
python -c "
import json
import config
with open(config.OUTPUTS_DIR / 'models' / 'metricas_propension.json') as f:
    m = json.load(f)
assert 0.5 <= m['auc'] <= 1.0
print(f'OK: modelo de propensión entrenado, AUC={m[\"auc\"]:.4f}')
"
```
Expected: `OK: modelo de propensión entrenado, AUC=<valor entre 0.5 y 1.0>`

- [ ] **Step 4: Commit**

```bash
git add notebooks/02_modelado.ipynb
git commit -m "feat: train and evaluate adoption propensity model"
```

---

## Task 18: [BLOQUEADO] Modelo de monto potencial a 12 meses

**No implementar hasta resolver la Pregunta Abierta #4.**

Esta tarea no tiene pasos de código porque SPEC.md no define la variable objetivo. Antes de escribir una sola línea, se necesita confirmación explícita sobre:

1. Qué cantidad exacta predice el modelo (ej.: incremento de saldo Invesbot + Inversión Virtual proyectado a 12 meses, saldo total esperado del portafolio, ticket potencial de inversión, etc.).
2. Con qué ventana de entrenamiento se construye el target, dado que el histórico disponible varía por fuente (`crean_inv_virtual_cdt` e `invesbot` tienen ~13 meses de datos; `crean_bolsillos` y `crean_fiducuenta` bastante menos fechas distintas) — no hay 12 meses completos y homogéneos para todas las fuentes.
3. Si el target se calcula solo sobre la población que ya adoptó (regresión condicional) o sobre toda la población de modelado (dos etapas: propensión + monto esperado).

**Una vez resuelto**, esta tarea se reescribe siguiendo el mismo patrón de Tasks 16-17 (dataset sin fuga → entrenar → evaluar con métricas de regresión como MAE/RMSE → guardar artefacto), y se inserta antes de la Task 19.

---

## Task 19: `scripts/export_powerbi.py` — export final para Power BI

**Files:**
- Create: `scripts/export_powerbi.py`

**Interfaces:**
- Consumes: `cliente_features`, `dim_cliente`, `dim_producto`, `dim_tiempo`, `fact_saldos` de `oro.db`.
- Produces: `outputs/powerbi/cliente_features.csv`, `outputs/powerbi/dim_cliente.csv`, `outputs/powerbi/dim_producto.csv`, `outputs/powerbi/dim_tiempo.csv`, `outputs/powerbi/fact_saldos.csv`.
- **Nota:** no incluye scores del modelo de propensión porque Task 18 (monto potencial) sigue bloqueada; si se quiere el score de propensión en el export, añadirlo aquí es un cambio de una línea (`df["score_propension"] = modelo.predict_proba(...)`) una vez resuelto el punto de las features de Task 16 con la población completa (no solo test set).

- [ ] **Step 1: Escribir el script**

```python
# scripts/export_powerbi.py
import config
from src.db_io import leer_tabla_sqlite

TABLAS = ["cliente_features", "dim_cliente", "dim_producto", "dim_tiempo", "fact_saldos"]


def main():
    destino = config.OUTPUTS_DIR / "powerbi"
    destino.mkdir(parents=True, exist_ok=True)
    for tabla in TABLAS:
        df = leer_tabla_sqlite(config.ORO_DB, tabla)
        ruta = destino / f"{tabla}.csv"
        df.to_csv(ruta, index=False)
        print(f"{tabla}: {len(df)} filas -> {ruta}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ejecutar**

Run: `python scripts/export_powerbi.py`
Expected: 5 líneas, una por tabla, sin errores.

- [ ] **Step 3: Verificar que los CSV son legibles y consistentes con oro.db**

Run:
```bash
python -c "
import pandas as pd
import config
from src.db_io import leer_tabla_sqlite

for tabla in ['cliente_features', 'dim_cliente', 'dim_producto', 'dim_tiempo', 'fact_saldos']:
    csv = pd.read_csv(config.OUTPUTS_DIR / 'powerbi' / f'{tabla}.csv')
    db = leer_tabla_sqlite(config.ORO_DB, tabla)
    assert len(csv) == len(db), f'{tabla}: csv={len(csv)} vs db={len(db)}'
print('OK: 5/5 exports de Power BI consistentes con oro.db')
"
```
Expected: `OK: 5/5 exports de Power BI consistentes con oro.db`

- [ ] **Step 4: Commit**

```bash
git add scripts/export_powerbi.py
git commit -m "feat: export gold layer tables to CSV for Power BI"
```
