# Pipeline CREAN v2 — Correcciones críticas y ampliación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir la fuga de información y la separación entrenamiento/scoring del pipeline existente, y ampliarlo con EDA de faltantes, validación estadística de variables, variables derivadas, modelos A/B + monto a 12 meses, auditoría de sesgo y dimensionamiento, según SPEC_V2.md.

**Architecture:** Se mantiene la arquitectura medallón existente (`bronce.db` → `plata.db` → `oro.db`) construida con pandas + sqlite3. **La mayor parte del trabajo nuevo consiste en extraer lógica a módulos testeables en `src/` y consumirla desde `plata/`, `oro/` y notebooks**, en vez de escribir lógica en los notebooks. Los notebooks quedan como capa de reporte: leen oro, llaman funciones de `src/`, escriben artefactos verificables en `outputs/`.

**Tech Stack:** Python 3.13, pandas 3.0, numpy, scikit-learn 1.9, scipy 1.18, matplotlib/seaborn, Jupyter (nbconvert), pytest, joblib.

## Punto de partida (código que YA existe, rama `worktree-pipeline-crean-sdd`)

**El trabajo se ejecuta en el worktree `C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\.claude\worktrees\pipeline-crean-sdd` (rama `worktree-pipeline-crean-sdd`), no en `main`.** `main` solo contiene `SPEC.md`, `SPEC_V2.md` y una copia suelta del plan v1.

| Archivo | Estado | Qué hace hoy |
|---|---|---|
| `config.py` | existe | Rutas de las 3 capas, `VENTANA_MESES_AGREGACION=6`, `RANDOM_STATE=42`, `TEST_SIZE=0.2` |
| `src/db_io.py` | existe | `extraer_zip_a_db`, `leer_tabla_sqlite`, `escribir_tabla_sqlite` |
| `src/aggregations.py` | existe | `agregar_serie_saldo` (snapshot / prom 6M / tendencia), `normalizar_producto_inv_virtual` |
| `bronce/extraccion.py` | existe | 7 zips → `bronce.db` |
| `bronce/diagnostico_calidad.py` | existe | Nulos, duplicados, encoding, integridad referencial → `outputs/quality/reporte_calidad.md` |
| `plata/transformacion.py` | existe | `clientes_plata` + 5 tablas de producto + `estimador_ingresos_plata` |
| `oro/construir_cliente_features.py` | existe | Tabla ancha 1 fila/cliente, `etiqueta_adopcion`, **`excluir_modelado`** (a eliminar) |
| `oro/construir_esquema_estrella.py` | existe | `dim_cliente`, `dim_producto`, `dim_tiempo`, `fact_saldos` (grano snapshot, **no mensual**) |
| `notebooks/01_eda.ipynb` | existe | 3 celdas: shape/nulos, tasas por variable sensible, población de modelado |
| `notebooks/02_modelado.ipynb` | existe | 4 celdas: dataset, chequeo de fuga *inline*, GradientBoosting, curva top-N |
| `scripts/export_powerbi.py` | existe | Exporta 5 tablas de `oro.db` a CSV |
| `scripts/run_pipeline.py` | existe | Orquestador bronce→plata→oro→export |
| `tests/` | existe | `test_db_io.py`, `test_aggregations.py`, `test_construir_cliente_features.py` |

**Lo que NO existe hoy y SPEC_V2 §1 da por existente:** `n_productos_inversion`, `saldo_total_invertido`, `pct_patrimonio_invertido`, `tiene_invesbot`, `tiene_inv_virtual`. `cliente_features` nunca las tuvo. Por eso la acción 1 de §1 no es un "recálculo" sino la **creación** de `n_productos_inversion_no_etiqueta` y `saldo_invertido_no_etiqueta` (Task 2). Las variables leaky se añaden igualmente a la lista negra del guard (Task 1) para que, si alguien las crea más adelante, el test falle.

**Prefijo real de columna:** el código usa `inversion_virtual_*`, SPEC_V2 §1 escribe `inv_virtual_*`. El guard cubre **las dos grafías**.

## Global Constraints

- **Entorno:** todos los comandos se ejecutan desde la raíz del worktree con el venv activo:
  ```bash
  source "C:/Users/natam/OneDrive/Desktop/Prueba-Tecnica-CREAN/venv/Scripts/activate"
  ```
  (PowerShell: `& "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\Activate.ps1"`)
- La arquitectura medallón no cambia: `bronce/` ingesta cruda, `plata/` transformaciones, `oro/` vista unificada.
- Etiqueta `adopcion` = `invesbot_saldo_snapshot > 0` OR `inversion_virtual_saldo_snapshot > 0`. CDT y Fiducuenta son señal, nunca etiqueta.
- **Ninguna variable derivada de Invesbot o Inversión Virtual puede ser predictora.** Prefijos prohibidos: `invesbot_`, `inv_virtual_`, `inversion_virtual_`. Lista negra explícita adicional en `src/fuga.py`.
- **Entrenamiento:** toda la base apta. **Scoring:** toda la base, sin excepción. Única exclusión: clientes sin ninguna señal en ninguna fuente.
- **No eliminar clientes** por falta de `estimador_ingreso` ni por falta de `desc_tipo_de_vivienda`.
- Toda división debe devolver **nulo** cuando el denominador es 0 o nulo, nunca `inf`.
- Toda decisión de imputación se registra en `outputs/decisiones/log_decisiones.csv` vía `src/log_decisiones.py`.
- **Clasificador por defecto: `sklearn.ensemble.HistGradientBoostingClassifier`** (reemplaza a `GradientBoostingClassifier`). Razón: soporta NaN nativamente — lo que activa la rama "no imputar" de la tabla de decisión de §3.2 — y es ~1 orden de magnitud más rápido sobre 860k filas. `random_state=config.RANDOM_STATE`.
- `RANDOM_STATE = 42`, `TEST_SIZE = 0.2` en todos los splits.
- **Si el AUC de un modelo de propensión supera 0.95 → detenerse e investigar fuga residual.** No continuar con las tareas siguientes.
- TDD estricto (test que falla primero) para `src/`, `plata/` y `oro/`. Para notebooks de EDA y modelado: **verificación de salida** (ejecutar con `nbconvert` + comprobar el artefacto escrito en `outputs/`), no TDD.
- Commit al final de cada tarea.

---

## Decisiones aplicadas — `DECISIONES.md` tiene precedencia

`DECISIONES.md` (raíz del proyecto) resuelve las 12 preguntas que este plan había marcado como PROVISIONAL, y **tiene precedencia sobre SPEC.md y SPEC_V2.md donde haya contradicción**. Ya no queda ninguna pregunta abierta bloqueante.

| # | Decisión | Efecto en el plan |
|---|---|---|
| D0 | Etiqueta **sin** exigir recencia + análisis de sensibilidad a 90 días | Se mantiene la etiqueta. **Trabajo nuevo:** `dias_desde_ultimo_dato` y `etiqueta_adopcion_reciente` (Task 2B), análisis de sensibilidad (Task 18B) |
| D1 | "Ninguna señal" = las 3 condiciones a la vez; `estimador_ing` SÍ cuenta como señal | Confirma lo planificado (Task 3) |
| D2 | Se conservan `sin_dato_financiero` (any) y `sin_dato_financiero_total` (all) | Confirma lo planificado (Task 3) |
| D3 | Se conserva `tendencia_6m` + **nueva** `tendencia_relativa_6m` | **Trabajo nuevo** en Tasks 8, 9; ambas compiten en Task 16 |
| D4 | **`FECHA_CORTE` global** = min(max_fecha de cada fuente) | **CAMBIA** Tasks 6, 7, 9 + **Task 0B nueva** (`src/fecha_corte.py`, `src/aggregations.py`) |
| D5 | Monto = los 4 productos, **descompuesto** en App vs. conservadores | **Trabajo nuevo** en Tasks 20, 25 |
| D6 | Proxy de género: **3 bandas** de interpretación, no umbral único | **CAMBIA** Tasks 12, 22 |
| D7 | **Lift condicional ≥ 1.5**; el Jaccard es inaplicable aquí | **CAMBIA** Tasks 12, 13, 14 |
| D8 | Antigüedad contra `FECHA_CORTE` global | **CAMBIA** Task 9 |
| D9 | `cv_saldo_liquido`: ventana fija 6M, mín. 3 meses **observados**, coeficiente de variación | **CAMBIA** Tasks 6, 8, 9 |
| D10 | `dif_ingreso_declarado_estimado` y `pct_dif_ingreso` | **CAMBIA** Tasks 4, 8 |
| D11 | `06_monto_12m.ipynb`, `07_auditoria_sesgo.ipynb` | Confirma lo planificado |

### Por qué D7 tenía que cambiar

El plan proponía Jaccard ≥ 0.50 entre "sin estimador" (~114.431) y "sin vivienda" (~585.000). Con esos tamaños, incluso si el conjunto menor estuviera **totalmente contenido** en el mayor, el Jaccard máximo sería 114.431/585.000 ≈ **0,196**. El umbral era inalcanzable por construcción y la regla nunca se habría activado. El lift condicional no depende de los tamaños relativos y sí mide lo que interesa: si faltar un bloque predice faltar el otro.

### Ambigüedades nuevas, resueltas con la regla general de `DECISIONES.md`

Ninguna es bloqueante. Cada una aplica la regla general (§final de DECISIONES.md) y queda registrada en el log de decisiones.

| # | Ambigüedad | Resolución | Regla aplicada |
|---|---|---|---|
| N1 | `dias_desde_ultimo_dato`: ¿"último dato" de qué fuente? | Máximo de la última fecha observada del cliente entre las 5 fuentes de saldo. Cliente sin ninguna fila de producto → **nulo + bandera**, nunca 0 ni un valor grande arbitrario | #1 (preservar información, no descartar clientes) |
| N2 | `tendencia_relativa_6m` con `saldo_prom_6m ≤ 0` | Nulo. Con denominador negativo (sobregiro) el signo del ratio se invierte y deja de significar "dirección del cambio" | #2 (más fácil de explicar) |
| N3 | ¿El corte global se aplica también a `estimador_ing`? | No: esa fuente no tiene columna `fecha`, así que no hay nada que filtrar. Se documenta explícitamente | #2 |
| N4 | Ventana de 90 días de la etiqueta alternativa (D0.2): ¿respecto a qué? | `FECHA_CORTE − 90 días`, coherente con `dias_desde_ultimo_dato` (D0.1) | #2 |
| N5 | "Mínimo 3 meses con dato" de D9: tras el forward fill el panel no tiene huecos | El panel emite una columna `observado` (1 = hubo observación real ese mes, 0 = valor arrastrado). El mínimo se cuenta sobre `observado`, no sobre filas | #1 |
| N6 | ¿El análisis de sensibilidad de D0 cubre los dos modelos? | Solo el Modelo A: es el principal y el único con positivos reales (en la población del Modelo B la etiqueta es 0 por construcción, §6.1) | #2 |
| N7 | Con `FECHA_CORTE` global, ¿qué pasa con los clientes cuya única observación es posterior al corte? | Quedan sin snapshot para esa fuente, igual que un cliente sin fila. Se **reporta el conteo** por fuente en el log; no se elimina a nadie de la base | #1 y #4 |

**Nota sobre el modelo de monto:** la única tarea genuinamente bloqueada en el plan v1 (su Task 18) sigue desbloqueada por SPEC_V2 §6.3, y D5 añade el requisito de descomposición.

---

## Estructura de archivos

```
(worktree)
├── config.py                              [MODIFICA]  + COLS_FINANCIERAS, UMBRAL_*
├── requirements.txt                       [MODIFICA]  + scipy
├── src/
│   ├── db_io.py                           [sin cambios]
│   ├── aggregations.py                    [MODIFICA]  fecha_corte obligatoria + n_obs_ventana (D4)
│   ├── fecha_corte.py                     [NUEVO]  FECHA_CORTE global (D4)
│   ├── fuga.py                            [NUEVO]  guard de fuga (§1.3)
│   ├── features_modelo.py                 [NUEVO]  selección de features A y B (§1.2, §6.1)
│   ├── derivadas.py                       [NUEVO]  división segura + variables derivadas, incl. tendencia_relativa_6m (D3) y cv_saldo_liquido (D9)
│   ├── panel_mensual.py                   [NUEVO]  regularización mensual con ffill + columna observado (§6.3.1, D9)
│   ├── feature_tests.py                   [NUEVO]  IV/WoE, Mann-Whitney, chi2/Cramér, BH, VIF (§4)
│   ├── decisiones.py                      [NUEVO]  tablas de decisión automáticas, incl. lift_condicional (D7) y bandas de proxy de género (D6)
│   ├── niveles.py                         [NUEVO]  cuartiles A/B/C/D por población (§6.2)
│   ├── monto.py                           [NUEVO]  crecimiento anualizado, backtest, escenarios (§6.3)
│   ├── auditoria_sesgo.py                 [NUEVO]  regla del 80%, tasas de selección (§6.6)
│   └── log_decisiones.py                  [NUEVO]  log de decisiones (§10)
├── tests/
│   ├── test_db_io.py                      [sin cambios]
│   ├── test_aggregations.py               [MODIFICA]  fecha_corte obligatoria + n_obs_ventana
│   ├── test_fecha_corte.py                [NUEVO]
│   ├── test_construir_cliente_features.py [MODIFICA]  excluir_modelado → apto_entrenamiento + D0
│   ├── test_fuga.py                       [NUEVO]
│   ├── test_features_modelo.py            [NUEVO]
│   ├── test_derivadas.py                  [NUEVO]
│   ├── test_panel_mensual.py              [NUEVO]
│   ├── test_feature_tests.py              [NUEVO]
│   ├── test_decisiones.py                 [NUEVO]
│   ├── test_niveles.py                    [NUEVO]
│   ├── test_monto.py                      [NUEVO]
│   ├── test_auditoria_sesgo.py            [NUEVO]
│   ├── test_log_decisiones.py             [NUEVO]
│   └── test_granularidad.py               [NUEVO]  §9
├── plata/transformacion.py                [MODIFICA]  + saldos_mensual_plata, primer_registro_plata, FECHA_CORTE cableada (D4)
├── oro/
│   ├── construir_cliente_features.py      [MODIFICA]  §1.1, §2, §5, §6.5
│   └── construir_esquema_estrella.py      [MODIFICA]  fact_saldos_mensual, dim_tiempo mensual
├── bronce/diagnostico_calidad.py          [MODIFICA]  §9
├── notebooks/
│   ├── 01_eda.ipynb                       [MODIFICA]  excluir_modelado → apto_entrenamiento
│   ├── 02_modelado.ipynb                  [MODIFICA]  §1, §2, §6.1, §6.2
│   ├── 03_eda_faltantes.ipynb             [NUEVO]  §3
│   ├── 04_validacion_variables.ipynb      [NUEVO]  §4
│   ├── 05_dimensionamiento.ipynb          [NUEVO]  §7
│   ├── 06_monto_12m.ipynb                 [NUEVO]  §6.3, descompuesto app/productos conservadores (D5)
│   └── 07_auditoria_sesgo.ipynb           [NUEVO]  §6.6, bandas de proxy de género (D6)
├── scripts/
│   ├── export_powerbi.py                  [MODIFICA]  §8 (8 archivos)
│   └── run_pipeline.py                    [MODIFICA]  + nuevos pasos
└── outputs/
    ├── decisiones/log_decisiones.csv
    ├── eda/faltantes_*.json|csv
    ├── models/*.pkl, *.json
    └── powerbi/*.csv
```

---

# FASE 1 — CORRECCIONES CRÍTICAS (bloqueantes)

> **Nada de las fases 2-6 se construye hasta que las Tasks 1-5 pasen sus verificaciones.**
> El gate está al final de la Task 5.

---

## Task 0: Preparación del entorno

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`

**Interfaces:**
- Produces: `config.COLS_FINANCIERAS`, `config.PRODUCTOS`, `config.PRODUCTOS_ETIQUETA`, `config.UMBRAL_IV_MINIMO`, `config.UMBRAL_AUC_FUGA`, `config.UMBRAL_AUC_PROXY_MODERADO`, `config.UMBRAL_AUC_PROXY_SUSTANCIAL`, `config.UMBRAL_LIFT_PERFIL_INCOMPLETO`, `config.UMBRAL_VIF`, `config.MESES_VALIDACION_BACKTEST`, `config.MESES_MINIMOS_CV_LIQUIDO`, `config.VENTANA_DIAS_ETIQUETA_RECIENTE`. Consumidos por casi todas las tareas.

- [ ] **Step 1: Añadir `scipy` a `requirements.txt`**

```
pandas>=2.2
numpy>=1.26
scikit-learn>=1.4
scipy>=1.11
matplotlib>=3.8
seaborn>=0.13
jupyter>=1.0
pyarrow>=15.0
pytest>=8.0
joblib>=1.3
```

- [ ] **Step 2: Añadir constantes compartidas a `config.py`**

Reemplazar el bloque final de `config.py` (desde el comentario `# --- Parámetros PROVISIONALES ...`) por:

```python
# --- Catálogos compartidos ---
COLS_FINANCIERAS = [
    "ingresos_mensuales",
    "total_egresos_mensuales",
    "total_activos",
    "total_pasivos",
    "total_patrimonio",
]

PRODUCTOS = [
    "cuenta_ahorro", "cuenta_corriente", "bolsillos",
    "fiducuenta", "cdt", "inversion_virtual", "invesbot",
]

# Productos que DEFINEN la etiqueta de adopción (nunca predictores)
PRODUCTOS_ETIQUETA = ["invesbot", "inversion_virtual"]

# Productos de inversión que NO definen la etiqueta (sí son predictores)
PRODUCTOS_INVERSION_NO_ETIQUETA = ["cdt", "fiducuenta"]

# Productos que componen el saldo líquido (SPEC_V2 §5)
PRODUCTOS_LIQUIDOS = ["cuenta_ahorro", "cuenta_corriente", "bolsillos"]

# --- Umbrales de decisión (SPEC_V2 + DECISIONES.md) ---
UMBRAL_IV_MINIMO = 0.02              # §4.1 y §6.5
UMBRAL_AUC_FUGA = 0.95               # §1: por encima => sospechar fuga residual
UMBRAL_AUC_PATRON_DEBIL = 0.60       # §3.2
UMBRAL_AUC_PATRON_INFORMATIVO = 0.70 # §3.2

# D6: bandas de interpretación para el proxy de género, no un umbral único.
# < MODERADO -> proxy mínimo. [MODERADO, SUSTANCIAL] -> proxy moderado.
# > SUSTANCIAL -> proxy sustancial (investigar mitigación).
UMBRAL_AUC_PROXY_MODERADO = 0.60     # §6.6.1 (D6)
UMBRAL_AUC_PROXY_SUSTANCIAL = 0.70   # §6.6.1 (D6)

# D7: el Jaccard es inaplicable (conjuntos desbalanceados: máximo alcanzable
# ~0.196, ver DECISIONES.md). Se reemplaza por lift condicional.
UMBRAL_LIFT_PERFIL_INCOMPLETO = 1.5  # §5/§6.5.2 (D7)

UMBRAL_VIF = 10.0                    # §4.5
UMBRAL_IMPACTO_DISPAR = 0.80         # §6.6.2
MESES_VALIDACION_BACKTEST = 3        # §6.3.4

# D9: ventana fija de volatilidad (reutiliza VENTANA_MESES_AGREGACION, ver abajo)
# + mínimo de meses con observación REAL (no arrastrada por forward fill).
MESES_MINIMOS_CV_LIQUIDO = 3         # §5 (D9)

# D0.2: ventana de la etiqueta alternativa del análisis de sensibilidad.
VENTANA_DIAS_ETIQUETA_RECIENTE = 90  # (D0, N4)

# VENTANA_MESES_AGREGACION = 6 confirmada por D9 para snapshot/prom_6m/tendencia_6m
# Y para la ventana de cv_saldo_liquido (misma ventana, mismo FECHA_CORTE global).
VENTANA_MESES_AGREGACION = 6
RANDOM_STATE = 42
TEST_SIZE = 0.2
```

- [ ] **Step 3: Instalar dependencias**

```bash
python -m pip install -r requirements.txt
```
Expected: termina sin errores.

- [ ] **Step 4: Verificar**

```bash
python -c "import config, scipy; print(config.UMBRAL_AUC_FUGA, config.UMBRAL_LIFT_PERFIL_INCOMPLETO, config.PRODUCTOS_ETIQUETA, scipy.__version__)"
```
Expected: `0.95 1.5 ['invesbot', 'inversion_virtual'] 1.18.0` (o superior)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config.py
git commit -m "✨feat: add shared catalogs and SPEC_V2 decision thresholds to config"
```

---

## Task 0B [NUEVO]: `src/fecha_corte.py` — fecha de corte global (D4)

**D4 cambia la propuesta provisional del plan v1**, que usaba `MAX(fecha)` **por fuente** para las ventanas de 6M (comentario "Pregunta Abierta #5" que aparecía en varias tareas). `DECISIONES.md` exige una única fecha de corte global:

```
FECHA_CORTE = min(max_fecha de cada una de las 5 fuentes de saldo)
```

Esta tarea crea el cálculo y lo cablea en `src/aggregations.py`, del que dependen **todas** las tablas de plata que usan `agregar_serie_saldo` (ya construidas en el plan v1). Es la única tarea de la Fase 1 que toca una función ya usada en producción, así que se hace con TDD estricto y se regenera `plata.db` al final.

**Files:**
- Create: `tests/test_fecha_corte.py`
- Create: `src/fecha_corte.py`
- Modify: `tests/test_aggregations.py`
- Modify: `src/aggregations.py`
- Modify: `plata/transformacion.py`

**Interfaces:**
- Produces: `calcular_fecha_corte(bronce_db=None) -> pd.Timestamp`. `agregar_serie_saldo(df, group_cols, fecha_corte, fecha_col="fecha", saldo_col="saldo", meses_ventana=6) -> pd.DataFrame` — **`fecha_corte` pasa a ser un parámetro obligatorio** (antes se calculaba internamente como `df[fecha_col].max()`); la salida gana la columna `n_obs_ventana` (conteo de filas crudas dentro de la ventana, por grupo). Consumidos por `plata/transformacion.py` (las 4 funciones de transformación de saldo del plan v1) y por Task 7 (`construir_saldos_mensual`).

- [ ] **Step 1: Escribir el test que falla — `src/fecha_corte.py`**

```python
# tests/test_fecha_corte.py
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_fecha_corte.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.fecha_corte'`

- [ ] **Step 3: Implementar `src/fecha_corte.py`**

```python
# src/fecha_corte.py
"""Fecha de corte global del pipeline (D4, DECISIONES.md).

D4 CAMBIA la propuesta provisional del plan v1 (corte por fuente): con cortes
por fuente cada cliente queda medido en un momento distinto y los saldos dejan
de ser comparables entre clientes. FECHA_CORTE = min(max_fecha de cada fuente)
es el punto más reciente en el que TODAS las fuentes tienen dato: toda ventana
de 6M, todo snapshot y toda antigüedad se miden contra esa única referencia.

estimador_ing NO participa (N3): no tiene columna `fecha`, no hay nada que cortar.
"""
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite

FUENTES_SALDO_CORTE = (
    "crean_aho_cte", "crean_bolsillos", "crean_fiducuenta",
    "crean_inv_virtual_cdt", "invesbot",
)


def calcular_fecha_corte(bronce_db=None) -> pd.Timestamp:
    bronce_db = bronce_db if bronce_db is not None else config.BRONCE_DB
    maximos = []
    for tabla in FUENTES_SALDO_CORTE:
        fechas = pd.to_datetime(leer_tabla_sqlite(bronce_db, tabla)["fecha"])
        maximos.append(fechas.max())
    return min(maximos)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_fecha_corte.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Escribir el test que falla — `agregar_serie_saldo` con `fecha_corte` explícito**

**Nota de estado real:** el código ya en el worktree (commits `2985534`, `c07ae6d`, `87b3a88`) no es exactamente el del plan v1 original — ya trae `n_obs_ventana` y ya distingue "sin datos en la ventana" (NaN real en `saldo_prom_6m`/`tendencia_6m`) de "confirmado cero". `tests/test_aggregations.py` ya tiene **3** tests (no 2): `test_agregar_serie_saldo_snapshot_es_el_mas_reciente`, `test_agregar_serie_saldo_promedio_y_tendencia`, `test_agregar_serie_saldo_sin_datos_en_ventana`. Ninguno pasa `fecha_corte` todavía — esta tarea SOLO añade ese parámetro; el comportamiento de NaN-vs-cero ya corregido **no se debe regresar**.

Añadir a `tests/test_aggregations.py` estos 2 tests nuevos:

```python
# tests/test_aggregations.py — añadir estos 2 tests nuevos, y reemplazar las
# 3 llamadas existentes a agregar_serie_saldo para pasar fecha_corte (ver abajo).

def test_agregar_serie_saldo_usa_fecha_corte_explicita_no_el_maximo_del_grupo():
    """D4: fecha_corte es un parámetro externo (global), NO se recalcula por
    grupo. Un cliente cuyo último dato es posterior al corte queda igual
    medido contra el corte, no contra su propio máximo."""
    df = pd.DataFrame({
        "numero_id": [1, 1, 1],
        "fecha": ["2026-01-01", "2026-03-01", "2026-08-01"],  # ago > corte
        "saldo": [100.0, 200.0, 999.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"))
    fila = resultado.iloc[0]
    assert fila["saldo_snapshot"] == 200.0          # último dato <= corte
    assert str(fila["fecha_snapshot"]) == "2026-03-01 00:00:00"


def test_agregar_serie_saldo_no_regresiona_nan_vs_cero_con_fecha_corte():
    """Guarda contra una regresión de esta MISMA tarea: al añadir fecha_corte,
    el caso 'sin datos en la ventana' debe seguir devolviendo NaN real, no 0.0
    (comportamiento ya corregido en el código actual, commit 87b3a88)."""
    df = pd.DataFrame({
        "numero_id": [1, 1, 2],
        "fecha": ["2026-01-01", "2026-06-01", "2020-01-01"],
        "saldo": [100.0, 300.0, 9999.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"), meses_ventana=6)
    fila_grupo2 = resultado[resultado["numero_id"] == 2].iloc[0]
    assert fila_grupo2["saldo_snapshot"] == 9999.0
    assert pd.isna(fila_grupo2["saldo_prom_6m"])
    assert pd.isna(fila_grupo2["tendencia_6m"])
    assert fila_grupo2["n_obs_ventana"] == 0
```

Y reemplazar las 3 llamadas existentes en ese mismo archivo (que llamaban a `agregar_serie_saldo(df, group_cols=[...])` sin `fecha_corte`) por estas versiones, que pasan `fecha_corte` explícitamente:

```python
def test_agregar_serie_saldo_snapshot_es_el_mas_reciente():
    df = pd.DataFrame({
        "numero_id": [1, 1, 1],
        "fecha": ["2026-01-01", "2026-03-01", "2026-06-01"],
        "saldo": [100.0, 200.0, 300.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"))
    fila = resultado.iloc[0]
    assert fila["saldo_snapshot"] == 300.0
    assert str(fila["fecha_snapshot"]) == "2026-06-01 00:00:00"
    assert fila["n_obs_ventana"] == 3  # las 3 filas caen dentro de la ventana de 6M


def test_agregar_serie_saldo_promedio_y_tendencia():
    # ventana de 6M hacia atrás desde 2026-06-01 => desde 2025-12-01
    df = pd.DataFrame({
        "numero_id": [1, 1, 1, 1],
        "fecha": ["2025-12-01", "2026-01-15", "2026-04-01", "2026-06-01"],
        "saldo": [100.0, 100.0, 300.0, 300.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"))
    fila = resultado.iloc[0]
    assert fila["saldo_prom_6m"] == 200.0  # promedio de las 4 filas
    assert fila["tendencia_6m"] == 200.0  # promedio 2a mitad (300) - promedio 1a mitad (100)
    assert fila["tenencia"] == 1
    assert fila["n_obs_ventana"] == 4  # las 4 filas caen dentro de la ventana


def test_agregar_serie_saldo_sin_datos_en_ventana():
    # Edge case: grupo con snapshot antiguo, nada en la ventana de 6M.
    # fecha_corte global = 2026-06-01, ventana = [2025-12-01, 2026-06-01].
    # grupo 1: datos en ventana (normal). grupo 2: solo datos antiguos (2020).
    df = pd.DataFrame({
        "numero_id": [1, 1, 2],
        "fecha": ["2026-01-01", "2026-06-01", "2020-01-01"],
        "saldo": [100.0, 300.0, 9999.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"), meses_ventana=6)
    fila_grupo2 = resultado[resultado["numero_id"] == 2].iloc[0]
    assert fila_grupo2["saldo_snapshot"] == 9999.0
    assert pd.isna(fila_grupo2["saldo_prom_6m"])  # sin datos en ventana -> NaN real, no 0
    assert pd.isna(fila_grupo2["tendencia_6m"])   # sin datos en ventana -> NaN real, no 0
    assert fila_grupo2["tenencia"] == 1
    assert fila_grupo2["n_obs_ventana"] == 0  # ningún registro cae en la ventana
```

- [ ] **Step 6: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_aggregations.py -v
```
Expected: FAIL — `TypeError: agregar_serie_saldo() missing 1 required positional argument: 'fecha_corte'`

- [ ] **Step 7: Modificar `src/aggregations.py`**

Reemplazar la firma y el cuerpo de `agregar_serie_saldo` (la única diferencia real respecto al código actual es la línea `fecha_corte = pd.Timestamp(fecha_corte)` en vez de `fecha_corte = df[fecha_col].max()`, más el filtro `df = df[df[fecha_col] <= fecha_corte]`; el resto — incluido NO rellenar `tendencia_6m`/`saldo_prom_6m` con 0.0 — se conserva tal cual):

```python
def agregar_serie_saldo(df, group_cols, fecha_corte, fecha_col="fecha", saldo_col="saldo", meses_ventana=6):
    """Snapshot / promedio 6M / tendencia 6M contra una fecha de corte GLOBAL (D4).

    `fecha_corte` ya no se infiere de `df[fecha_col].max()` (eso mediría cada
    fuente, o peor, cada grupo, en un momento distinto). Se recibe siempre como
    parámetro externo — típicamente `src.fecha_corte.calcular_fecha_corte()` —
    para que TODA la base quede medida contra la misma referencia temporal.
    """
    df = df.copy()
    df[fecha_col] = pd.to_datetime(df[fecha_col])
    fecha_corte = pd.Timestamp(fecha_corte)
    df = df[df[fecha_col] <= fecha_corte]   # D4: se descarta lo posterior al corte
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
    n_obs = (
        ventana.groupby(group_cols, as_index=False)[saldo_col]
        .size()
        .rename(columns={"size": "n_obs_ventana"})
    )

    primera_mitad = ventana[ventana[fecha_col] < mitad].groupby(group_cols)[saldo_col].mean()
    segunda_mitad = ventana[ventana[fecha_col] >= mitad].groupby(group_cols)[saldo_col].mean()
    tendencia = (segunda_mitad - primera_mitad).rename("tendencia_6m").reset_index()

    out = (
        snapshot.merge(prom6m, on=group_cols, how="left")
        .merge(n_obs, on=group_cols, how="left")
        .merge(tendencia, on=group_cols, how="left")
    )
    # Sin datos en la ventana de 6M => dejar NaN real (no se puede calcular), no
    # confundir "sin observación" con "confirmado plano/cero". n_obs_ventana es
    # el único campo que sí es seguro rellenar con 0, porque un conteo de 0 es
    # un hecho, no una suposición. NO rellenar saldo_prom_6m ni tendencia_6m.
    out["n_obs_ventana"] = out["n_obs_ventana"].fillna(0).astype(int)
    out["tenencia"] = 1
    return out
```

- [ ] **Step 8: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_aggregations.py -v
```
Expected: `6 passed` — los 3 tests de `agregar_serie_saldo` ya existentes en el worktree (`snapshot_es_el_mas_reciente`, `promedio_y_tendencia`, `sin_datos_en_ventana`), ahora con `fecha_corte`, más los 2 nuevos de esta tarea (`usa_fecha_corte_explicita_no_el_maximo_del_grupo`, `no_regresiona_nan_vs_cero_con_fecha_corte`), más `test_normalizar_producto_inv_virtual_corrige_casing_inconsistente` (sin cambios, no llama a `agregar_serie_saldo`).

- [ ] **Step 9: Cablear `FECHA_CORTE` en `plata/transformacion.py`**

Las 4 funciones de transformación de saldo del plan v1 (`transformar_aho_cte`, `transformar_producto_unico`, `transformar_cdt_inversion_virtual`, y el bucle de `FUENTES_PRODUCTO_UNICO`) llaman a `agregar_serie_saldo(df, group_cols=[...], meses_ventana=config.VENTANA_MESES_AGREGACION)` sin `fecha_corte`. Añadir el import y calcular la fecha una sola vez:

```python
# plata/transformacion.py — cabecera
from src.fecha_corte import calcular_fecha_corte

FECHA_CORTE = None  # se resuelve en tiempo de ejecución, ver _fecha_corte()


def _fecha_corte():
    global FECHA_CORTE
    if FECHA_CORTE is None:
        FECHA_CORTE = calcular_fecha_corte()
    return FECHA_CORTE
```

Y reemplazar las 4 llamadas a `agregar_serie_saldo(...)` del plan v1 (que no pasaban `fecha_corte`) por estas versiones:

```python
# transformar_aho_cte (Task 7 del plan v1)
def transformar_aho_cte():
    df = leer_tabla_sqlite(config.BRONCE_DB, "crean_aho_cte")
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id", "producto"], fecha_corte=_fecha_corte(),
        meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "aho_cte_plata")
    return resultado


# transformar_producto_unico (Task 8 del plan v1 — bolsillos/fiducuenta/invesbot)
def transformar_producto_unico(tabla_bronce, tabla_plata_destino):
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id", "producto"], fecha_corte=_fecha_corte(),
        meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, tabla_plata_destino)
    return resultado


# transformar_cdt_inversion_virtual (Task 9 del plan v1)
def transformar_cdt_inversion_virtual():
    df = leer_tabla_sqlite(config.BRONCE_DB, "crean_inv_virtual_cdt")
    df["producto"] = df["producto"].apply(normalizar_producto_inv_virtual).map(MAPA_PRODUCTO_SLUG)
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id", "producto"], fecha_corte=_fecha_corte(),
        meses_ventana=config.VENTANA_MESES_AGREGACION)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "cdt_inversion_virtual_plata")
    return resultado
```

- [ ] **Step 10: Regenerar `plata.db` sobre datos reales y verificar la fecha de corte**

```bash
python -c "
from src.fecha_corte import calcular_fecha_corte
fc = calcular_fecha_corte()
print(f'FECHA_CORTE = {fc.date()}')
"
```
Expected: imprime `FECHA_CORTE = 2026-0X-XX` (el mínimo de los 5 máximos reales; DECISIONES.md estimaba `2026-06-01`, **verificar el valor real**).

```bash
python -m plata.transformacion
```
Expected: las 4 tablas de producto se regeneran sin error contra el corte global.

- [ ] **Step 11: Commit**

```bash
git add src/fecha_corte.py src/aggregations.py plata/transformacion.py tests/test_fecha_corte.py tests/test_aggregations.py
git commit -m "✨feat: compute global FECHA_CORTE and wire it into agregar_serie_saldo (D4)"
```

---

## Task 1 [NUEVO]: `src/fuga.py` — test automático anti-fuga (SPEC_V2 §1.3)

Esta es **la** verificación de la sección 1. Es código nuevo, TDD estricto.

**Files:**
- Create: `tests/test_fuga.py`
- Create: `src/fuga.py`

**Interfaces:**
- Produces: `PREFIJOS_FUGA: tuple[str, ...]`, `COLUMNAS_FUGA_EXPLICITAS: frozenset[str]`, `FugaDeInformacionError(AssertionError)`, `columnas_con_fuga(columnas: Iterable[str]) -> list[str]`, `validar_sin_fuga(columnas: Iterable[str], contexto: str = "entrenamiento") -> bool`. Consumidos por `src/features_modelo.py` (Task 4), `notebooks/02_modelado.ipynb` (Task 5) y `notebooks/06_monto_12m.ipynb` (Task 21).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_fuga.py
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_fuga.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.fuga'`

- [ ] **Step 3: Implementar `src/fuga.py`**

```python
# src/fuga.py
"""Guardia contra fuga de información en el conjunto de entrenamiento.

SPEC_V2 §1: la etiqueta `adopcion` se define como saldo activo en Invesbot y/o
Inversión Virtual, así que ninguna variable derivada de esos dos productos puede
ser predictora. Este módulo es la implementación del "test automático que falle
si alguna variable con prefijo invesbot_ o inv_virtual_ entra al conjunto de
entrenamiento" (§1, acción 3).
"""
from typing import Iterable

# `inversion_virtual_` es la grafía que realmente generan plata/oro;
# `inv_virtual_` es la que usa SPEC_V2. Se cubren las dos.
PREFIJOS_FUGA = ("invesbot_", "inv_virtual_", "inversion_virtual_")

# Variables sin prefijo delator que igualmente contienen la etiqueta porque
# agregan los productos que la definen (SPEC_V2 §1).
COLUMNAS_FUGA_EXPLICITAS = frozenset({
    "etiqueta_adopcion",
    "tiene_invesbot",
    "tiene_inv_virtual",
    "tiene_inversion_virtual",
    "n_productos_inversion",
    "saldo_total_invertido",
    "pct_patrimonio_invertido",
    "n_productos_total",          # cuenta TODOS los productos, incluidos los de la etiqueta
    "tiene_historial_inversion",  # §6.3: incluye historial en Invesbot/IV
    "monto_estimado_12m",         # salida del modelo de monto, no entrada
})


class FugaDeInformacionError(AssertionError):
    """Se lanza cuando una variable prohibida entra al conjunto de entrenamiento."""


def columnas_con_fuga(columnas: Iterable[str]) -> list[str]:
    """Devuelve, ordenadas, las columnas que no pueden ser predictoras."""
    return sorted(
        c for c in columnas
        if c.startswith(PREFIJOS_FUGA) or c in COLUMNAS_FUGA_EXPLICITAS
    )


def validar_sin_fuga(columnas: Iterable[str], contexto: str = "entrenamiento") -> bool:
    """Lanza FugaDeInformacionError si alguna columna prohibida está presente."""
    encontradas = columnas_con_fuga(columnas)
    if encontradas:
        raise FugaDeInformacionError(
            f"Fuga de información en {contexto}: {encontradas}. "
            f"SPEC_V2 §1 prohíbe toda variable derivada de Invesbot o Inversión Virtual."
        )
    return True
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_fuga.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/fuga.py tests/test_fuga.py
git commit -m "✨feat: add leakage guard that fails on invesbot_/inv_virtual_ features (SPEC_V2 1.3)"
```

---

## Task 2 [MODIFICA]: agregados de inversión sin la etiqueta (SPEC_V2 §1.1)

**Files:**
- Modify: `tests/test_construir_cliente_features.py`
- Modify: `oro/construir_cliente_features.py`

**Interfaces:**
- Consumes: `config.PRODUCTOS_INVERSION_NO_ETIQUETA`.
- Produces: en `cliente_features` las columnas `n_productos_inversion_no_etiqueta: int` (0-2) y `saldo_invertido_no_etiqueta: float`. Consumidas por `src/features_modelo.py` (Task 4) y `notebooks/04_validacion_variables.ipynb` (Task 17).

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `tests/test_construir_cliente_features.py`:

```python
def test_agregados_de_inversion_excluyen_los_productos_de_la_etiqueta(tmp_path, monkeypatch):
    """SPEC_V2 §1.1: n_productos_inversion_no_etiqueta y saldo_invertido_no_etiqueta
    se calculan SOLO con CDT y Fiducuenta. Un cliente con saldo enorme en Invesbot
    y cero en CDT/Fiducuenta debe quedar en 0 en ambas columnas."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    escribir_tabla_sqlite(pd.DataFrame({"numero_id": [301, 302]}), plata_db, "clientes_plata")

    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    escribir_tabla_sqlite(vacia, plata_db, "aho_cte_plata")
    escribir_tabla_sqlite(vacia, plata_db, "bolsillos_plata")

    # 302: 700 en Fiducuenta -> cuenta
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(302, "fiducuenta", saldo_snapshot=700.0)]),
        plata_db, "fiducuenta_plata",
    )
    # 302: 300 en CDT -> cuenta. 301: nada.
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(302, "cdt", saldo_snapshot=300.0)]),
        plata_db, "cdt_inversion_virtual_plata",
    )
    # 301: 9.000.000 en Invesbot -> NO debe contar
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(301, "invesbot", saldo_snapshot=9_000_000.0)]),
        plata_db, "invesbot_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata",
    )

    r = construir_cliente_features().set_index("numero_id")

    assert r.loc[301, "n_productos_inversion_no_etiqueta"] == 0
    assert r.loc[301, "saldo_invertido_no_etiqueta"] == 0.0
    assert r.loc[302, "n_productos_inversion_no_etiqueta"] == 2
    assert r.loc[302, "saldo_invertido_no_etiqueta"] == 1000.0
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_construir_cliente_features.py::test_agregados_de_inversion_excluyen_los_productos_de_la_etiqueta -v
```
Expected: FAIL con `KeyError: 'n_productos_inversion_no_etiqueta'`

- [ ] **Step 3: Implementar**

En `oro/construir_cliente_features.py`, sustituir la línea `PRODUCTOS = [...]` por un import desde config y añadir el cálculo justo después del bloque de `etiqueta_adopcion`:

```python
# oro/construir_cliente_features.py — cabecera
import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite

PRODUCTOS = config.PRODUCTOS
```

```python
    # --- SPEC_V2 §1.1: agregados de inversión que NO tocan la etiqueta ---
    # Solo CDT y Fiducuenta. Nunca Invesbot ni Inversión Virtual: sumarlos
    # reintroduciría la etiqueta dentro de las predictoras.
    cols_saldo_no_etiqueta = [
        f"{p}_saldo_snapshot" for p in config.PRODUCTOS_INVERSION_NO_ETIQUETA
    ]
    base["saldo_invertido_no_etiqueta"] = base[cols_saldo_no_etiqueta].fillna(0.0).sum(axis=1)
    base["n_productos_inversion_no_etiqueta"] = (
        (base[cols_saldo_no_etiqueta].fillna(0.0) > 0).sum(axis=1).astype(int)
    )
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_construir_cliente_features.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add oro/construir_cliente_features.py tests/test_construir_cliente_features.py
git commit -m "✨feat: add label-free investment aggregates from CDT/Fiducuenta only (SPEC_V2 1.1)"
```

---

## Task 2B [NUEVO]: `dias_desde_ultimo_dato` + `etiqueta_adopcion_reciente` (D0)

D0 mantiene la etiqueta de adopción actual (saldo positivo, sin exigir recencia) porque un dato antiguo evidencia falta de dato reciente, no abandono del producto. Pero exige dos cosas nuevas: (1) un control de calidad de dato por cliente, y (2) una etiqueta alternativa para el análisis de sensibilidad de la Task 18B.

**Files:**
- Modify: `oro/construir_cliente_features.py`
- Modify: `tests/test_construir_cliente_features.py`

**Interfaces:**
- Consumes: `src.fecha_corte.calcular_fecha_corte` (Task 0B), `config.VENTANA_DIAS_ETIQUETA_RECIENTE`.
- Produces: en `cliente_features` las columnas `{producto}_fecha_snapshot` por cada uno de los 7 productos (antes se descartaban en el pivote), `dias_desde_ultimo_dato: Int64` (nulo si el cliente no tiene ninguna fila de producto), `sin_dato_reciente: int` (1 si no hay ninguna fecha), `etiqueta_adopcion_reciente: int` (N4: exige que el snapshot de Invesbot o Inversión Virtual esté a `config.VENTANA_DIAS_ETIQUETA_RECIENTE` días de `FECHA_CORTE`). Consumida por `notebooks/02_modelado.ipynb` (Task 18B).

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_construir_cliente_features.py`:

```python
def test_recencia_de_dato_y_etiqueta_alternativa(tmp_path, monkeypatch):
    """D0: dias_desde_ultimo_dato es el máximo de fecha_snapshot entre las 5
    fuentes de saldo (N1); etiqueta_adopcion_reciente exige que el snapshot de
    Invesbot/Inversión Virtual esté dentro de la ventana de recencia (N4)."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)
    monkeypatch.setattr(
        "oro.construir_cliente_features.calcular_fecha_corte",
        lambda: pd.Timestamp("2026-06-01"))

    escribir_tabla_sqlite(
        _clientes_plata([601, 602, 603]), plata_db, "clientes_plata")
    vacia = _plata_vacia_producto()
    for t in ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata", "cdt_inversion_virtual_plata"]:
        escribir_tabla_sqlite(vacia, plata_db, t)
    # 601: saldo positivo en invesbot, snapshot RECIENTE (dentro de 90 días del corte)
    # 602: saldo positivo en invesbot, snapshot ANTIGUO (fuera de la ventana)
    # 603: sin ninguna fila de producto -> sin dato en absoluto
    escribir_tabla_sqlite(pd.DataFrame([
        _tabla_producto(601, "invesbot", saldo_snapshot=500.0, fecha_snapshot="2026-05-15"),
        _tabla_producto(602, "invesbot", saldo_snapshot=500.0, fecha_snapshot="2025-01-01"),
    ]), plata_db, "invesbot_plata")
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata")
    _panel_y_primer_registro_vacios(plata_db)

    r = construir_cliente_features().set_index("numero_id")

    assert r.loc[601, "etiqueta_adopcion"] == 1        # etiqueta principal: sin exigir recencia
    assert r.loc[602, "etiqueta_adopcion"] == 1        # también positivo, aunque el dato sea viejo
    assert r.loc[601, "etiqueta_adopcion_reciente"] == 1
    assert r.loc[602, "etiqueta_adopcion_reciente"] == 0   # fuera de la ventana de 90 días
    assert r.loc[603, "etiqueta_adopcion_reciente"] == 0

    assert r.loc[601, "dias_desde_ultimo_dato"] == 17
    assert pd.isna(r.loc[603, "dias_desde_ultimo_dato"])
    assert r.loc[603, "sin_dato_reciente"] == 1
    assert r.loc[601, "sin_dato_reciente"] == 0
```

Esto requiere que el helper `_tabla_producto` (definido en el plan v1) acepte `fecha_snapshot` como argumento — si no lo acepta ya, añadir el parámetro con default `"2026-06-01"` antes de esta tarea.

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_construir_cliente_features.py::test_recencia_de_dato_y_etiqueta_alternativa -v
```
Expected: FAIL con `KeyError: 'dias_desde_ultimo_dato'`

- [ ] **Step 3: Dejar de descartar `fecha_snapshot` en el pivote**

En `oro/construir_cliente_features.py`, en `_pivotear_producto` (Task 11 del plan v1), cambiar:

```python
    df = df[df["producto"] == producto].drop(columns=["producto", "fecha_snapshot"])
    df = df.rename(columns={
        "saldo_snapshot": f"{producto}_saldo_snapshot",
        "saldo_prom_6m": f"{producto}_saldo_prom_6m",
        "tendencia_6m": f"{producto}_tendencia_6m",
        "tenencia": f"{producto}_tenencia",
    })
```

por:

```python
    df = df[df["producto"] == producto].drop(columns=["producto"])
    df = df.rename(columns={
        "saldo_snapshot": f"{producto}_saldo_snapshot",
        "saldo_prom_6m": f"{producto}_saldo_prom_6m",
        "tendencia_6m": f"{producto}_tendencia_6m",
        "tenencia": f"{producto}_tenencia",
        "fecha_snapshot": f"{producto}_fecha_snapshot",   # D0: ya no se descarta
    })
```

- [ ] **Step 4: Añadir las dos funciones y cablearlas**

```python
from src.fecha_corte import calcular_fecha_corte   # ya importado en Task 9 si se hizo antes


def agregar_recencia_dato(base: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    """D0, requisito 1: control de calidad de dato por cliente (N1).

    `dias_desde_ultimo_dato` = FECHA_CORTE − máxima fecha_snapshot entre las 5
    fuentes de saldo. Un cliente sin NINGUNA fila de producto queda en NULO +
    bandera `sin_dato_reciente`, nunca en 0 ni en un valor grande arbitrario.
    """
    out = base.copy()
    fecha_cols = [f"{p}_fecha_snapshot" for p in config.PRODUCTOS]
    presentes = [c for c in fecha_cols if c in out.columns]
    ultimo_dato = out[presentes].max(axis=1)
    out["dias_desde_ultimo_dato"] = (fecha_corte - ultimo_dato).dt.days.astype("Int64")
    out["sin_dato_reciente"] = ultimo_dato.isna().astype(int)
    return out


def agregar_etiqueta_adopcion_reciente(base: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    """D0, análisis de sensibilidad: etiqueta alternativa que SÍ exige recencia
    (N4: ventana de `config.VENTANA_DIAS_ETIQUETA_RECIENTE` días desde
    FECHA_CORTE). Solo se usa para comparar contra la etiqueta principal en la
    Task 18B — la etiqueta principal (`etiqueta_adopcion`) no cambia."""
    out = base.copy()
    ventana = config.VENTANA_DIAS_ETIQUETA_RECIENTE
    reciente_invesbot = (
        (out["invesbot_saldo_snapshot"] > 0)
        & ((fecha_corte - out["invesbot_fecha_snapshot"]).dt.days <= ventana)
    ).fillna(False)
    reciente_iv = (
        (out["inversion_virtual_saldo_snapshot"] > 0)
        & ((fecha_corte - out["inversion_virtual_fecha_snapshot"]).dt.days <= ventana)
    ).fillna(False)
    out["etiqueta_adopcion_reciente"] = (reciente_invesbot | reciente_iv).astype(int)
    return out
```

Y en `construir_cliente_features()`, justo después del bloque de `etiqueta_adopcion` (Task 11 del plan v1):

```python
    fecha_corte = calcular_fecha_corte()
    base = agregar_recencia_dato(base, fecha_corte)
    base = agregar_etiqueta_adopcion_reciente(base, fecha_corte)
```

- [ ] **Step 5: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_construir_cliente_features.py -v
```
Expected: todos los tests existentes de este archivo pasan + el nuevo.

- [ ] **Step 6: Regenerar oro y comprobar sobre datos reales**

```bash
python -m oro.construir_cliente_features
```

```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
assert {'dias_desde_ultimo_dato','sin_dato_reciente','etiqueta_adopcion_reciente'} <= set(df.columns)
# etiqueta_adopcion_reciente <= etiqueta_adopcion: exigir recencia solo puede RESTAR positivos
assert (df['etiqueta_adopcion_reciente'] <= df['etiqueta_adopcion']).all()
n_dif = int((df['etiqueta_adopcion'] != df['etiqueta_adopcion_reciente']).sum())
print(f'OK D0 — {n_dif:,} clientes cambian de etiqueta bajo el criterio de recencia estricta')
print(df['dias_desde_ultimo_dato'].describe().to_string())
"
```
Expected: `OK D0 — <N> clientes cambian de etiqueta bajo el criterio de recencia estricta` + el resumen estadístico de `dias_desde_ultimo_dato`.

- [ ] **Step 7: Commit**

```bash
git add oro/construir_cliente_features.py tests/test_construir_cliente_features.py
git commit -m "✨feat: add dias_desde_ultimo_dato and sensitivity label etiqueta_adopcion_reciente (D0)"
```

---

## Task 3 [MODIFICA]: `apto_entrenamiento` + `tiene_historial_producto` (SPEC_V2 §2)

Elimina `excluir_modelado` y lo reemplaza por dos banderas separadas. Es la corrección de la sección 2.

**Files:**
- Modify: `tests/test_construir_cliente_features.py`
- Modify: `oro/construir_cliente_features.py`
- Modify: `plata/transformacion.py` (usar `config.COLS_FINANCIERAS`, añadir `sin_dato_financiero_total`)
- Modify: `bronce/diagnostico_calidad.py` (usar `config.COLS_FINANCIERAS`)

**Interfaces:**
- Produces: en `clientes_plata` la columna `sin_dato_financiero_total: bool` (las 5 columnas financieras nulas). En `cliente_features` las columnas `tiene_historial_producto: int`, `sin_ninguna_senal: int`, `apto_entrenamiento: int`. **`excluir_modelado` deja de existir.** Consumidas por notebooks 01, 02, 05, 06, 07 y `scripts/export_powerbi.py`.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_construir_cliente_features.py`, hacer tres cosas:

**(a)** En el test de la Task 2 (`test_agregados_de_inversion_excluyen_los_productos_de_la_etiqueta`), añadir la columna nueva al fixture de `clientes_plata`, porque a partir de este cambio `construir_cliente_features` la lee:

```python
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [301, 302],
                      "sin_dato_financiero_total": [False, False]}),
        plata_db, "clientes_plata",
    )
```

**(b)** Reemplazar el test existente `test_construir_cliente_features_logica_de_negocio` por esta versión, y **(c)** añadir el nuevo test que le sigue:

```python
def test_construir_cliente_features_logica_de_negocio(tmp_path, monkeypatch):
    """
    Cubre las dos reglas de negocio más consecuentes: etiqueta_adopcion y las
    banderas de población de SPEC_V2 §2. Clientes sintéticos:
      - 201: saldo positivo en invesbot -> etiqueta_adopcion == 1
      - 202: saldo positivo solo en CDT -> etiqueta_adopcion == 0
      - 203: sin producto, sin estimador, sin financieros -> apto_entrenamiento == 0
      - 204: sin producto pero CON estimador -> apto_entrenamiento == 1
    """
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    clientes_plata = pd.DataFrame({
        "numero_id": [201, 202, 203, 204],
        "sin_dato_financiero_total": [False, False, True, True],
    })
    escribir_tabla_sqlite(clientes_plata, plata_db, "clientes_plata")

    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    escribir_tabla_sqlite(vacia, plata_db, "aho_cte_plata")
    escribir_tabla_sqlite(vacia, plata_db, "bolsillos_plata")
    escribir_tabla_sqlite(vacia, plata_db, "fiducuenta_plata")

    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(202, "cdt", saldo_snapshot=1000.0)]),
        plata_db, "cdt_inversion_virtual_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(201, "invesbot", saldo_snapshot=500.0)]),
        plata_db, "invesbot_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [204], "estimador_ingreso": [3_000_000.0],
                      "tiene_estimador_ingreso": [True]}),
        plata_db, "estimador_ingresos_plata",
    )

    resultado = construir_cliente_features().set_index("numero_id")

    assert resultado.loc[201, "etiqueta_adopcion"] == 1
    assert resultado.loc[202, "etiqueta_adopcion"] == 0
    assert resultado.loc[201, "cdt_tenencia"] == 0
    assert resultado.loc[202, "invesbot_tenencia"] == 0

    # SPEC_V2 §2: excluir_modelado desaparece
    assert "excluir_modelado" not in resultado.columns

    # tiene_historial_producto: separado de la aptitud para entrenar
    assert resultado.loc[201, "tiene_historial_producto"] == 1
    assert resultado.loc[202, "tiene_historial_producto"] == 1
    assert resultado.loc[203, "tiene_historial_producto"] == 0
    assert resultado.loc[204, "tiene_historial_producto"] == 0

    # única exclusión admitida: sin señal en NINGUNA fuente
    assert resultado.loc[203, "apto_entrenamiento"] == 0
    assert resultado.loc[203, "sin_ninguna_senal"] == 1
    # 204 no tiene producto pero sí estimador -> entra al entrenamiento como negativo legítimo
    assert resultado.loc[204, "apto_entrenamiento"] == 1
    assert resultado.loc[204, "sin_ninguna_senal"] == 0


def test_cliente_sin_producto_pero_con_datos_financieros_entra_al_entrenamiento(tmp_path, monkeypatch):
    """SPEC_V2 §2: los ~90.467 clientes con datos financieros completos y sin
    historial de producto son ejemplos negativos legítimos y necesarios.
    No pueden quedar fuera del entrenamiento ni del scoring."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [401], "sin_dato_financiero_total": [False]}),
        plata_db, "clientes_plata",
    )
    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    for t in ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
              "cdt_inversion_virtual_plata", "invesbot_plata"]:
        escribir_tabla_sqlite(vacia, plata_db, t)
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata",
    )

    r = construir_cliente_features().set_index("numero_id")
    assert r.loc[401, "tiene_historial_producto"] == 0
    assert r.loc[401, "apto_entrenamiento"] == 1   # tiene señal financiera
    assert r.loc[401, "sin_ninguna_senal"] == 0
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_construir_cliente_features.py -v
```
Expected: FAIL con `KeyError: 'sin_dato_financiero_total'` / `assert 'excluir_modelado' not in ...`

- [ ] **Step 3: Añadir `sin_dato_financiero_total` en plata**

En `plata/transformacion.py`, reemplazar la constante local y la función `limpiar_clientes`:

```python
# plata/transformacion.py — reemplaza la definición local de COLS_FINANCIERAS
COLS_FINANCIERAS = config.COLS_FINANCIERAS


def limpiar_clientes():
    df = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    df = df.drop_duplicates(subset="numero_id", keep="first")
    # `any`: bandera descriptiva conservadora (Pregunta Abierta #3)
    df["sin_dato_financiero"] = df[COLS_FINANCIERAS].isnull().any(axis=1)
    # `all`: "ninguna señal financiera", único insumo válido para la exclusión de SPEC_V2 §2
    df["sin_dato_financiero_total"] = df[COLS_FINANCIERAS].isnull().all(axis=1)
    df["capacidad_ahorro"] = df["ingresos_mensuales"] - df["total_egresos_mensuales"]
    escribir_tabla_sqlite(df, config.PLATA_DB, "clientes_plata")
    return df
```

En `bronce/diagnostico_calidad.py`, reemplazar la constante local:

```python
COLS_FINANCIERAS = config.COLS_FINANCIERAS
```

- [ ] **Step 4: Reemplazar `excluir_modelado` en oro**

En `oro/construir_cliente_features.py`, sustituir el bloque de `excluir_modelado` por:

```python
    # --- SPEC_V2 §2: población de entrenamiento vs. población de scoring ---
    # Se scorea a TODA la base. La única exclusión admitida es "sin ninguna señal
    # en ninguna fuente": ni producto, ni estimador de ingreso, ni datos financieros.
    tenencia_cols = [f"{p}_tenencia" for p in PRODUCTOS]
    base["tiene_historial_producto"] = (base[tenencia_cols].sum(axis=1) > 0).astype(int)

    base["sin_ninguna_senal"] = (
        (base["tiene_historial_producto"] == 0)
        & (~base["tiene_estimador_ingreso"])
        & base["sin_dato_financiero_total"].fillna(False).astype(bool)
    ).astype(int)

    base["apto_entrenamiento"] = (1 - base["sin_ninguna_senal"]).astype(int)
```

Y el bloque `__main__`:

```python
if __name__ == "__main__":
    df = construir_cliente_features()
    print(f"cliente_features: {len(df)} filas, {df.shape[1]} columnas")
    print(f"tasa adopción: {df['etiqueta_adopcion'].mean():.4f}")
    print(f"con historial de producto: {df['tiene_historial_producto'].sum()}")
    print(f"sin ninguna señal (única exclusión): {df['sin_ninguna_senal'].sum()}")
    print(f"aptos para entrenamiento: {df['apto_entrenamiento'].sum()}")
```

- [ ] **Step 5: Ejecutar los tests**

```bash
python -m pytest tests/ -v
```
Expected: `8 passed` (2 db_io + 3 aggregations + 3 cliente_features)... y `tests/test_fuga.py` aparte. Total esperado: `14 passed`.

- [ ] **Step 6: Regenerar plata y oro sobre datos reales**

```bash
python -m plata.transformacion
```
Expected: `clientes_plata: 860223 filas, 260 con sin_dato_financiero` (+ las 5 tablas de producto y estimador).

```bash
python -m oro.construir_cliente_features
```
Expected: imprime las 5 líneas nuevas. **`sin ninguna señal` debe ser ≤ 81** (el plan v1 midió 90.548 excluidos de los cuales solo 81 tenían nulos financieros; con la regla correcta la exclusión se limita a ese subconjunto).

- [ ] **Step 7: Verificar la corrección de §2 sobre datos reales**

```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
assert 'excluir_modelado' not in df.columns, 'excluir_modelado sigue existiendo'
assert len(df) == 860223
n_excl = int(df['sin_ninguna_senal'].sum())
n_apto = int(df['apto_entrenamiento'].sum())
n_sin_hist = int((df['tiene_historial_producto'] == 0).sum())
print(f'sin_ninguna_senal={n_excl}  apto_entrenamiento={n_apto}  sin_historial_producto={n_sin_hist}')
assert n_excl <= 81, f'la exclusion sigue siendo demasiado amplia: {n_excl}'
assert n_apto + n_excl == len(df)
# los clientes sin historial de producto pero con datos deben estar DENTRO del entrenamiento
sin_hist_aptos = int(((df['tiene_historial_producto'] == 0) & (df['apto_entrenamiento'] == 1)).sum())
assert sin_hist_aptos > 90000, f'solo {sin_hist_aptos} clientes sin historial entran al entrenamiento'
print(f'OK SPEC_V2 §2: {sin_hist_aptos} clientes sin historial de producto entran al entrenamiento')
"
```
Expected: `OK SPEC_V2 §2: 90467 clientes sin historial de producto entran al entrenamiento` (el número exacto puede variar ±100; lo verificable es `>90000` y `sin_ninguna_senal <= 81`).

- [ ] **Step 8: Commit**

```bash
git add oro/construir_cliente_features.py plata/transformacion.py bronce/diagnostico_calidad.py tests/test_construir_cliente_features.py
git commit -m "🐛fix: replace excluir_modelado with apto_entrenamiento + tiene_historial_producto (SPEC_V2 2)"
```

---

## Task 4 [NUEVO]: `src/features_modelo.py` — selección de predictoras (SPEC_V2 §1.2, §6.1)

**Files:**
- Create: `tests/test_features_modelo.py`
- Create: `src/features_modelo.py`

**Interfaces:**
- Consumes: `src.fuga.validar_sin_fuga`, `config.COLS_FINANCIERAS`.
- Produces:
  - `COLUMNAS_NO_FEATURE: frozenset[str]` — ids, banderas de población y etiquetas.
  - `COLUMNAS_SENSIBLES_EXCLUIDAS: tuple[str, ...]` = `("desc_genero",)` (§6.4: solo género se excluye).
  - `features_modelo_a(columnas: Iterable[str]) -> list[str]`
  - `features_modelo_b(columnas: Iterable[str]) -> list[str]`
  - Ambas llaman a `validar_sin_fuga` antes de devolver. Consumidas por notebooks 02, 04, 06, 07.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_features_modelo.py
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


def test_ambas_funciones_lanzan_si_se_cuela_una_columna_prohibida(monkeypatch):
    import src.features_modelo as fm
    # simula un descuido: alguien saca invesbot_ de la lista de no-features
    monkeypatch.setattr(fm, "COLUMNAS_NO_FEATURE", frozenset())
    monkeypatch.setattr(fm, "PREFIJOS_EXCLUIDOS_A", ())
    with pytest.raises(FugaDeInformacionError):
        fm.features_modelo_a(["invesbot_saldo_snapshot", "ingresos_mensuales"])
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_features_modelo.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.features_modelo'`

- [ ] **Step 3: Implementar `src/features_modelo.py`**

```python
# src/features_modelo.py
"""Selección de predictoras para los dos modelos de propensión (SPEC_V2 §6.1).

Modelo A (completo): capacidad financiera + comportamiento en productos que NO
definen la etiqueta + variables derivadas.
Modelo B (cold-start): SOLO capacidad financiera y derivadas de ella.

Toda salida pasa por `validar_sin_fuga` antes de devolverse: la selección y el
guard viven juntos para que sea imposible entrenar saltándose la comprobación.
"""
from typing import Iterable

import config
from src.fuga import PREFIJOS_FUGA, validar_sin_fuga

# Identificadores, etiquetas y banderas de población: nunca son predictoras.
COLUMNAS_NO_FEATURE = frozenset({
    "numero_id",
    "etiqueta_adopcion",
    "apto_entrenamiento",
    "tiene_historial_producto",
    "sin_ninguna_senal",
    "score_propension",
    "nivel_prioridad",
    "modelo_usado",
    "monto_estimado_12m",
    "monto_conservador_12m",
    "monto_base_12m",
    "monto_optimista_12m",
})

# SPEC_V2 §6.4: de las tres demográficas, SOLO género queda fuera del modelo.
# grupo_edad y desc_tipo_de_vivienda entran (esta última sujeta a §6.5).
COLUMNAS_SENSIBLES_EXCLUIDAS = ("desc_genero",)

# Prefijos que el Modelo A no puede usar: los de fuga.
PREFIJOS_EXCLUIDOS_A = PREFIJOS_FUGA

# Modelo B: lista blanca. Nada de producto, ni siquiera indirectamente.
# Son las columnas financieras + sus derivadas de §5 que no tocan saldos de producto.
COLUMNAS_MODELO_B = tuple(config.COLS_FINANCIERAS) + (
    "capacidad_ahorro",
    "estimador_ingreso",
    "tiene_estimador_ingreso",
    "falta_estimador",
    "ratio_egreso_ingreso",
    "pct_ahorro_ingreso",
    "ratio_pasivo_activo",
    "patrimonio_por_ingreso",
    "dif_ingreso_declarado_estimado",   # D10 (antes gap_ingreso_estimado_declarado)
    "pct_dif_ingreso",                  # D10 (antes pct_gap_ingreso)
    "sin_dato_financiero",
    "grupo_edad",
    "desc_tipo_de_vivienda",
    "tiene_dato_vivienda",
    "perfil_incompleto",
    "desc_segmento",
)


def features_modelo_a(columnas: Iterable[str]) -> list[str]:
    """Predictoras del Modelo A: todo menos ids, etiquetas, fuga y género."""
    feats = [
        c for c in columnas
        if c not in COLUMNAS_NO_FEATURE
        and c not in COLUMNAS_SENSIBLES_EXCLUIDAS
        and not c.startswith(PREFIJOS_EXCLUIDOS_A)
    ]
    validar_sin_fuga(feats, contexto="Modelo A")
    return feats


def features_modelo_b(columnas: Iterable[str]) -> list[str]:
    """Predictoras del Modelo B: lista blanca de capacidad financiera."""
    presentes = set(columnas)
    feats = [c for c in COLUMNAS_MODELO_B if c in presentes]
    validar_sin_fuga(feats, contexto="Modelo B")
    return feats
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_features_modelo.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Verificar contra las columnas REALES de `cliente_features`**

```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
from src.features_modelo import features_modelo_a, features_modelo_b
cols = leer_tabla_sqlite(config.ORO_DB, 'cliente_features').columns
a = features_modelo_a(cols)
b = features_modelo_b(cols)
print(f'Modelo A: {len(a)} features')
print(f'Modelo B: {len(b)} features -> {b}')
assert not any(c.startswith(('invesbot_','inv_virtual_','inversion_virtual_')) for c in a)
assert not any(c.startswith(('invesbot_','inv_virtual_','inversion_virtual_')) for c in b)
print('OK: ninguna variable de la etiqueta entra a A ni a B')
"
```
Expected: imprime los conteos y `OK: ninguna variable de la etiqueta entra a A ni a B`

- [ ] **Step 6: Commit**

```bash
git add src/features_modelo.py tests/test_features_modelo.py
git commit -m "✨feat: add guarded feature selection for models A and B (SPEC_V2 1.2, 6.1)"
```

---

## Task 5 [MODIFICA]: corregir `02_modelado.ipynb` — GATE de la Fase 1

Corrige el notebook existente para consumir la población y las features nuevas. **No** implementa aún los modelos A/B completos (eso es la Task 18); aquí solo se verifica que las correcciones de §1 y §2 se sostienen sobre datos reales.

**Files:**
- Modify: `notebooks/01_eda.ipynb` (celda 3: `excluir_modelado` → `apto_entrenamiento`)
- Modify: `notebooks/02_modelado.ipynb` (celdas 0, 1 y 2)

**Interfaces:**
- Consumes: `cliente_features` (Tasks 2-3), `src.features_modelo.features_modelo_a`.
- Produces: `outputs/eda/poblacion_entrenamiento.csv`, `outputs/models/metricas_propension.json` con la clave `auc`. **Reemplaza** `outputs/eda/poblacion_modelado.csv`.

- [ ] **Step 1: Corregir la celda 3 de `01_eda.ipynb`**

Reemplazar el contenido de la tercera celda de código por:

```python
saldo_cols = [c for c in df.columns if c.endswith("_saldo_snapshot")]
resumen_saldos = df.groupby("etiqueta_adopcion")[saldo_cols + ["capacidad_ahorro"]].mean()
print(resumen_saldos)

# SPEC_V2 §2: la población de entrenamiento es toda la base apta (única exclusión:
# clientes sin ninguna señal en ninguna fuente). La de scoring es TODA la base.
poblacion_entrenamiento = df.loc[df["apto_entrenamiento"] == 1, ["numero_id"]]
poblacion_entrenamiento.to_csv(config.OUTPUTS_DIR / "eda" / "poblacion_entrenamiento.csv", index=False)

print(f"población de entrenamiento: {len(poblacion_entrenamiento)} de {len(df)} clientes")
print(f"excluidos (sin ninguna señal): {int(df['sin_ninguna_senal'].sum())}")
print(f"sin historial de producto (negativos legítimos, SÍ entrenan): "
      f"{int(((df['tiene_historial_producto'] == 0) & (df['apto_entrenamiento'] == 1)).sum())}")
```

- [ ] **Step 2: Corregir las celdas 0-2 de `02_modelado.ipynb`**

Celda 0:

```python
import sys
sys.path.insert(0, "..")

import pandas as pd
from sklearn.model_selection import train_test_split

import config
from src.db_io import leer_tabla_sqlite
from src.features_modelo import features_modelo_a
from src.fuga import validar_sin_fuga

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")

# SPEC_V2 §2: entrenamiento sobre toda la base apta. Los clientes sin productos
# son ejemplos negativos legítimos y necesarios, no se excluyen.
entrenables = df[df["apto_entrenamiento"] == 1].reset_index(drop=True)

feature_cols = features_modelo_a(entrenables.columns)   # lanza si hay fuga
X = pd.get_dummies(
    entrenables[feature_cols],
    columns=[c for c in ["desc_segmento", "grupo_edad", "desc_tipo_de_vivienda"]
             if c in feature_cols],
    dummy_na=False,
)
y = entrenables["etiqueta_adopcion"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=config.TEST_SIZE, random_state=config.RANDOM_STATE, stratify=y
)
print(f"entrenables: {len(entrenables)} de {len(df)}")
print(f"train: {X_train.shape}, test: {X_test.shape}, tasa adopción train: {y_train.mean():.4f}")
```

Celda 1 — el chequeo inline se sustituye por la llamada al guard compartido:

```python
# SPEC_V2 §1.3: el guard es el mismo que cubre tests/test_fuga.py.
# Se ejecuta sobre las columnas REALES que entran al fit (post get_dummies),
# no solo sobre la lista previa.
validar_sin_fuga(X_train.columns, contexto="fit del modelo de propensión")
print(f"OK: {X_train.shape[1]} columnas de entrenamiento, ninguna derivada de la etiqueta")
```

Celda 2:

```python
import json
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score

# HistGradientBoostingClassifier maneja NaN nativamente (SPEC_V2 §3.2 depende de
# esto): no hace falta imputar los ~179 clientes con financieros nulos.
modelo = HistGradientBoostingClassifier(random_state=config.RANDOM_STATE)
modelo.fit(X_train, y_train)

proba = modelo.predict_proba(X_test)[:, 1]
pred = modelo.predict(X_test)

metricas = {
    "auc": float(roc_auc_score(y_test, proba)),
    "precision": float(precision_score(y_test, pred, zero_division=0)),
    "recall": float(recall_score(y_test, pred, zero_division=0)),
    "n_train": int(len(X_train)),
    "n_test": int(len(X_test)),
    "n_features": int(X_train.shape[1]),
}
print(metricas)

# SPEC_V2 §1: por encima de 0.95 se asume fuga residual y se detiene el trabajo.
assert metricas["auc"] <= config.UMBRAL_AUC_FUGA, (
    f"AUC={metricas['auc']:.4f} > {config.UMBRAL_AUC_FUGA}: sospecha de fuga residual. "
    "Investigar antes de continuar (SPEC_V2 §1)."
)

(config.OUTPUTS_DIR / "models").mkdir(parents=True, exist_ok=True)
joblib.dump(modelo, config.OUTPUTS_DIR / "models" / "propension_adopcion.pkl")
with open(config.OUTPUTS_DIR / "models" / "metricas_propension.json", "w") as f:
    json.dump(metricas, f, indent=2)
```

En la celda 3 (curva top-N), sustituir la única referencia a `X_test_filled` por `X_test` si existiera; la celda actual solo usa `proba` e `y_test`, así que no requiere cambios.

- [ ] **Step 3: Ejecutar los dos notebooks**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb
```
Expected: exit code 0.

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_modelado.ipynb
```
Expected: exit code 0. Si falla con `FugaDeInformacionError` o con el `assert` del AUC, **el gate no pasa**: investigar antes de seguir.

- [ ] **Step 4: GATE — verificación conjunta de SPEC_V2 §1 y §2**

```bash
python -c "
import json
import pandas as pd
import config
from src.db_io import leer_tabla_sqlite
from src.features_modelo import features_modelo_a
from src.fuga import validar_sin_fuga

df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')

# §1 — sin fuga
validar_sin_fuga(features_modelo_a(df.columns), contexto='gate fase 1')

# §1 — AUC por debajo del umbral de sospecha
with open(config.OUTPUTS_DIR / 'models' / 'metricas_propension.json') as f:
    m = json.load(f)
assert 0.5 <= m['auc'] <= config.UMBRAL_AUC_FUGA, m

# §2 — toda la base es scoreable, solo se excluye quien no tiene ninguna señal
pop = pd.read_csv(config.OUTPUTS_DIR / 'eda' / 'poblacion_entrenamiento.csv')
assert len(pop) == int(df['apto_entrenamiento'].sum())
assert len(df) - len(pop) == int(df['sin_ninguna_senal'].sum()) <= 81

print(f'GATE OK — AUC={m[\"auc\"]:.4f} | entrenables={len(pop)} | excluidos={len(df)-len(pop)}')
"
```
Expected: `GATE OK — AUC=0.xxxx | entrenables=860142 | excluidos=81` (cifras aproximadas; lo verificable son las tres aserciones).

- [ ] **Step 5: Ejecutar toda la batería de tests**

```bash
python -m pytest tests/ -v
```
Expected: `20 passed` (2 db_io + 3 aggregations + 3 cliente_features + 6 fuga + 6 features_modelo)

- [ ] **Step 6: Commit**

```bash
git add notebooks/01_eda.ipynb notebooks/02_modelado.ipynb
git commit -m "🐛fix: wire leakage guard and full training population into notebooks (SPEC_V2 1, 2)"
```

> **A partir de aquí las fases 2-6 pueden ejecutarse. Si el gate de la Task 5 no pasó, detenerse.**

---

# FASE 2 — Panel mensual y variables derivadas

---

## Task 6 [NUEVO]: `src/panel_mensual.py` — regularización mensual con forward fill (SPEC_V2 §6.3.1)

**Files:**
- Create: `tests/test_panel_mensual.py`
- Create: `src/panel_mensual.py`

**Interfaces:**
- Produces: `construir_panel_mensual(df, group_cols, fecha_col="fecha", saldo_col="saldo", mes_max=None) -> pd.DataFrame` con columnas `group_cols + ["mes", "saldo_mes", "observado"]`, donde `mes` es un `Timestamp` de primer día de mes y `observado` vale 1 si ese mes tuvo una fila real en `df` y 0 si el valor viene del forward fill (D9, N5: el mínimo de meses con dato de `cv_saldo_liquido` se cuenta sobre `observado`, no sobre filas del panel, porque tras el ffill el panel no tiene huecos que contar). `primer_mes_por_grupo(df, group_cols, fecha_col="fecha") -> pd.DataFrame` con `group_cols + ["primer_mes"]`. Consumidas por `plata/transformacion.py` (Task 7), `src/derivadas.py` (Task 8, `cv_saldo_liquido`), `oro/construir_esquema_estrella.py` (Task 24) y `notebooks/06_monto_12m.ipynb` (Task 21).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_panel_mensual.py
import pandas as pd

from src.panel_mensual import construir_panel_mensual, primer_mes_por_grupo


def test_forward_fill_no_interpola_linealmente():
    """SPEC_V2 §6.3.1: un saldo persiste hasta el siguiente movimiento.
    Entre enero (100) y abril (400) los meses intermedios valen 100, NO 200/300."""
    df = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-04-10"],
        "saldo": [100.0, 400.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    saldos = panel.sort_values("mes")["saldo_mes"].tolist()
    assert saldos == [100.0, 100.0, 100.0, 400.0]


def test_dentro_de_un_mes_gana_la_ultima_observacion():
    df = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-05", "2026-01-28"],
        "saldo": [100.0, 250.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    assert panel["saldo_mes"].tolist() == [250.0]


def test_cada_grupo_arranca_en_su_primer_mes_y_todos_terminan_en_mes_max():
    df = pd.DataFrame({
        "numero_id": [1, 2],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-03-10"],
        "saldo": [100.0, 50.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    assert (panel["numero_id"] == 1).sum() == 3   # ene, feb, mar
    assert (panel["numero_id"] == 2).sum() == 1   # solo mar
    assert panel["mes"].max() == pd.Timestamp("2026-03-01")


def test_mes_es_siempre_el_primer_dia_del_mes():
    df = pd.DataFrame({
        "numero_id": [1], "producto": ["cdt"],
        "fecha": ["2026-02-27"], "saldo": [10.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    assert panel["mes"].tolist() == [pd.Timestamp("2026-02-01")]


def test_mes_max_explicito_extiende_el_panel():
    df = pd.DataFrame({
        "numero_id": [1], "producto": ["cdt"],
        "fecha": ["2026-01-15"], "saldo": [100.0],
    })
    panel = construir_panel_mensual(
        df, group_cols=["numero_id", "producto"], mes_max=pd.Timestamp("2026-03-01")
    )
    assert panel["saldo_mes"].tolist() == [100.0, 100.0, 100.0]


def test_grupos_independientes_no_se_contaminan():
    df = pd.DataFrame({
        "numero_id": [1, 2, 2],
        "producto": ["cdt", "cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-01-15", "2026-03-01"],
        "saldo": [100.0, 999.0, 5.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    c1 = panel[panel["numero_id"] == 1].sort_values("mes")["saldo_mes"].tolist()
    assert c1 == [100.0, 100.0, 100.0]   # el 999 del cliente 2 no se filtra


def test_primer_mes_por_grupo():
    df = pd.DataFrame({
        "numero_id": [1, 1, 2],
        "fecha": ["2026-03-01", "2025-11-20", "2026-02-05"],
        "saldo": [1.0, 2.0, 3.0],
    })
    r = primer_mes_por_grupo(df, group_cols=["numero_id"]).set_index("numero_id")
    assert r.loc[1, "primer_mes"] == pd.Timestamp("2025-11-01")
    assert r.loc[2, "primer_mes"] == pd.Timestamp("2026-02-01")


def test_observado_distingue_mes_real_de_mes_arrastrado():
    """D9 (N5): `observado` marca los meses con fila real en `df`. Entre enero
    (real) y abril (real) los meses de por medio (feb, mar) son forward fill:
    observado=0, aunque `saldo_mes` tenga un valor no nulo."""
    df = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-04-10"],
        "saldo": [100.0, 400.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    panel = panel.sort_values("mes")
    assert panel["observado"].tolist() == [1, 0, 0, 1]
    assert panel["saldo_mes"].tolist() == [100.0, 100.0, 100.0, 400.0]
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_panel_mensual.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.panel_mensual'`

- [ ] **Step 3: Implementar `src/panel_mensual.py`**

```python
# src/panel_mensual.py
"""Regularización de series de saldo a frecuencia mensual (SPEC_V2 §6.3.1).

Un saldo persiste hasta el siguiente movimiento: se rellena hacia adelante
(forward fill), NUNCA se interpola linealmente. Interpolar inventaría
movimientos intermedios que no ocurrieron.

La aritmética de meses se hace sobre un índice entero (`anio * 12 + mes - 1`)
en vez de con Periods, porque la construcción de la rejilla necesita repetir
filas y sumar offsets de forma vectorizada sobre 10⁶-10⁷ filas.
"""
import numpy as np
import pandas as pd


def _a_indice_mes(fechas: pd.Series) -> pd.Series:
    return fechas.dt.year * 12 + (fechas.dt.month - 1)


def _a_timestamp_mes(indice: pd.Series) -> pd.Series:
    return pd.to_datetime({
        "year": indice // 12,
        "month": indice % 12 + 1,
        "day": 1,
    })


def primer_mes_por_grupo(df, group_cols, fecha_col="fecha"):
    """Primer mes con registro para cada grupo, como Timestamp de día 1."""
    d = df[list(group_cols) + [fecha_col]].copy()
    d[fecha_col] = pd.to_datetime(d[fecha_col])
    r = d.groupby(list(group_cols), as_index=False)[fecha_col].min()
    r["primer_mes"] = _a_timestamp_mes(_a_indice_mes(r[fecha_col]))
    return r.drop(columns=[fecha_col])


def construir_panel_mensual(df, group_cols, fecha_col="fecha", saldo_col="saldo",
                            mes_max=None):
    """Panel cliente-producto-mes con forward fill.

    Para cada grupo: se toma el ÚLTIMO saldo observado dentro de cada mes, se
    completa la rejilla desde el primer mes del grupo hasta `mes_max` (por
    defecto, el mes máximo observado en `df`), y se rellena hacia adelante.
    """
    group_cols = list(group_cols)
    d = df[group_cols + [fecha_col, saldo_col]].copy()
    d[fecha_col] = pd.to_datetime(d[fecha_col])
    d["idx_mes"] = _a_indice_mes(d[fecha_col])

    # Último saldo observado dentro de cada mes: este mes SÍ tuvo una fila real.
    mensual = (
        d.sort_values(fecha_col)
        .groupby(group_cols + ["idx_mes"], as_index=False)[saldo_col]
        .last()
        .rename(columns={saldo_col: "saldo_mes"})
    )
    mensual["observado"] = 1

    idx_max = (
        int(_a_indice_mes(pd.Series([pd.Timestamp(mes_max)])).iloc[0])
        if mes_max is not None
        else int(mensual["idx_mes"].max())
    )

    # Rejilla completa: de idx_ini(grupo) a idx_max, un mes por fila
    inicio = mensual.groupby(group_cols, as_index=False)["idx_mes"].min()
    inicio = inicio.rename(columns={"idx_mes": "idx_ini"})
    inicio["n_meses"] = idx_max - inicio["idx_ini"] + 1
    inicio = inicio[inicio["n_meses"] > 0]

    rejilla = inicio.loc[inicio.index.repeat(inicio["n_meses"])].copy()
    rejilla["idx_mes"] = (
        rejilla["idx_ini"] + rejilla.groupby(group_cols).cumcount()
    )
    rejilla = rejilla.drop(columns=["idx_ini", "n_meses"])

    panel = (
        rejilla.merge(mensual, on=group_cols + ["idx_mes"], how="left")
        .sort_values(group_cols + ["idx_mes"])
        .reset_index(drop=True)
    )
    # D9 (N5): marcar ANTES del ffill. Un mes sin fila real llega aquí con
    # observado=NaN; tras fillna(0) queda 0, distinguible de los meses reales (1).
    panel["observado"] = panel["observado"].fillna(0).astype(int)
    panel["saldo_mes"] = panel.groupby(group_cols)["saldo_mes"].ffill()
    panel["mes"] = _a_timestamp_mes(panel["idx_mes"])
    return panel[group_cols + ["mes", "saldo_mes", "observado"]]
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_panel_mensual.py -v
```
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/panel_mensual.py tests/test_panel_mensual.py
git commit -m "✨feat: add monthly panel regularization with forward fill (SPEC_V2 6.3.1)"
```

---

## Task 7 [MODIFICA]: `plata/transformacion.py` — `saldos_mensual_plata` y `primer_registro_plata`

**Files:**
- Modify: `plata/transformacion.py`
- Create: `tests/test_transformacion_mensual.py`

**Interfaces:**
- Consumes: `src.panel_mensual.construir_panel_mensual`, `primer_mes_por_grupo`, `src.fecha_corte.calcular_fecha_corte` (Task 0B).
- Produces: tabla `saldos_mensual_plata` en `plata.db` (`numero_id, producto, mes, saldo_mes, observado`) y `primer_registro_plata` (`numero_id, primer_mes`, mínimo sobre las 5 fuentes de saldo). **Las 5 fuentes se regularizan contra el mismo `mes_max`, derivado de `FECHA_CORTE` global (D4)** — no cada una contra su propio máximo. Consumidas por Task 8 (`cv_saldo_liquido`/antigüedad), Task 21 (modelo de monto) y Task 24 (`fact_saldos_mensual`).

- [ ] **Step 1: Escribir el test que falla**

```python
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
    assert set(r["producto"]) == {"cuenta_ahorro", "bolsillos", "fiducuenta", "invesbot", "cdt"}
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_transformacion_mensual.py -v
```
Expected: FAIL con `ImportError: cannot import name 'construir_saldos_mensual'`

- [ ] **Step 3: Implementar en `plata/transformacion.py`**

Añadir el import y las dos funciones:

```python
import pandas as pd

from src.fecha_corte import calcular_fecha_corte
from src.panel_mensual import construir_panel_mensual, primer_mes_por_grupo

# (numero_id, producto, saldo) por fuente, con el normalizador que aplica a cada una
FUENTES_SALDO = [
    ("crean_aho_cte", False),
    ("crean_bolsillos", False),
    ("crean_fiducuenta", False),
    ("invesbot", False),
    ("crean_inv_virtual_cdt", True),   # requiere normalizar_producto_inv_virtual
]


def _leer_fuente_saldo(tabla_bronce, normalizar_inv_virtual):
    df = leer_tabla_sqlite(config.BRONCE_DB, tabla_bronce)
    if normalizar_inv_virtual:
        df["producto"] = df["producto"].apply(normalizar_producto_inv_virtual)
    df["producto"] = df["producto"].map(MAPA_PRODUCTO_SLUG)
    assert df["producto"].notna().all(), f"valores de producto sin mapear en {tabla_bronce}"
    return df[["numero_id", "producto", "fecha", "saldo"]]


def construir_saldos_mensual():
    """Panel cliente-producto-mes con forward fill (SPEC_V2 §6.3.1 y §8).

    D4 CAMBIA la propuesta provisional del plan v1 ("cada fuente contra su
    propio máximo"): las 5 fuentes se regularizan contra el MISMO `mes_max`,
    derivado de `FECHA_CORTE` global (Task 0B). Con cortes por fuente cada
    cliente-producto queda medido en un momento distinto; con un `mes_max`
    compartido, ninguna fuente aporta meses que las demás no puedan ver.
    """
    fecha_corte = calcular_fecha_corte()
    paneles = []
    for tabla, normalizar in FUENTES_SALDO:
        df = _leer_fuente_saldo(tabla, normalizar)
        panel = construir_panel_mensual(
            df, group_cols=["numero_id", "producto"], mes_max=fecha_corte)
        paneles.append(panel)
    resultado = pd.concat(paneles, ignore_index=True)
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "saldos_mensual_plata")
    return resultado


def construir_primer_registro():
    """Primer mes con registro del cliente en CUALQUIER fuente de saldo.
    Insumo de `antiguedad_relacion_meses` (SPEC_V2 §5)."""
    minimos = []
    for tabla, normalizar in FUENTES_SALDO:
        df = _leer_fuente_saldo(tabla, normalizar)
        minimos.append(primer_mes_por_grupo(df, group_cols=["numero_id"]))
    resultado = (
        pd.concat(minimos, ignore_index=True)
        .groupby("numero_id", as_index=False)["primer_mes"].min()
    )
    escribir_tabla_sqlite(resultado, config.PLATA_DB, "primer_registro_plata")
    return resultado
```

Añadir al bloque `__main__`:

```python
    mensual = construir_saldos_mensual()
    print(f"saldos_mensual_plata: {len(mensual)} filas, "
          f"{mensual['mes'].min()} -> {mensual['mes'].max()}")
    primer = construir_primer_registro()
    print(f"primer_registro_plata: {len(primer)} filas")
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_transformacion_mensual.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Ejecutar sobre datos reales y reportar volumen (SPEC_V2 §8)**

```bash
python -m plata.transformacion
```
Expected: incluye `saldos_mensual_plata: <N> filas, 2025-06-01 00:00:00 -> 2026-06-01 00:00:00` y `primer_registro_plata: <M> filas`.

```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
from src.fecha_corte import calcular_fecha_corte
m = leer_tabla_sqlite(config.PLATA_DB, 'saldos_mensual_plata')
print(f'saldos_mensual_plata: {len(m):,} filas')
print(m.groupby('producto').size().to_string())
assert not m.duplicated(subset=['numero_id','producto','mes']).any()
assert m['saldo_mes'].notna().all(), 'el forward fill dejó huecos'
assert len(m) < 30_000_000, f'volumen desproporcionado: {len(m):,}'
# D4: TODAS las fuentes comparten el mismo mes_max, derivado de FECHA_CORTE global
m['mes'] = __import__('pandas').to_datetime(m['mes'])
fc = calcular_fecha_corte()
assert m['mes'].max().to_period('M') == fc.to_period('M'), (m['mes'].max(), fc)
print(f'OK: panel mensual único por cliente-producto-mes, sin huecos, corte global={fc.date()}')
"
```
Expected: imprime el conteo por producto y `OK: panel mensual único por cliente-producto-mes, sin huecos, corte global=2026-0X-XX`. **Anotar el número de filas** — SPEC_V2 §8 lo pide explícitamente.

- [ ] **Step 6: Commit**

```bash
git add plata/transformacion.py tests/test_transformacion_mensual.py
git commit -m "✨feat: build monthly balance panel and first-record table in silver layer"
```

---

## Task 8 [NUEVO]: `src/derivadas.py` — división segura y variables derivadas (SPEC_V2 §5)

**Files:**
- Create: `tests/test_derivadas.py`
- Create: `src/derivadas.py`

**Interfaces:**
- Consumes: `config.PRODUCTOS`, `config.PRODUCTOS_LIQUIDOS`, `config.PRODUCTOS_ETIQUETA`, `config.COLS_FINANCIERAS`, `config.VENTANA_MESES_AGREGACION`, `config.MESES_MINIMOS_CV_LIQUIDO`.
- Produces:
  - `division_segura(numerador, denominador, denominador_positivo=False) -> pd.Series` (NaN si denominador 0/nulo, nunca `inf`; con `denominador_positivo=True` también NaN si el denominador es negativo — D3/N2)
  - `agregar_ratios_financieros(df) -> pd.DataFrame` — produce `dif_ingreso_declarado_estimado` y `pct_dif_ingreso` (D10, nombres renombrados desde `gap_ingreso_estimado_declarado`/`pct_gap_ingreso`)
  - `agregar_agregados_producto(df) -> pd.DataFrame`
  - `agregar_tendencia_relativa(df) -> pd.DataFrame` — añade `{producto}_tendencia_relativa_6m` por cada producto de `config.PRODUCTOS` (D3)
  - `agregar_banderas_faltantes(df, cols_por_bloque: dict[str, list[str]]) -> pd.DataFrame`
  - `agregar_vivienda_como_categoria(df, etiqueta="Sin dato") -> pd.DataFrame`
  - `resumen_cv_saldo_liquido(panel_mensual, productos_liquidos, fecha_corte, meses_ventana=6, meses_minimos=3) -> pd.DataFrame` con `numero_id, cv_saldo_liquido, cv_saldo_liquido_insuficiente` (D9 — reemplaza a `resumen_panel_liquido`/`volatilidad_saldo_liquido` del borrador anterior)
  - Consumidas por `oro/construir_cliente_features.py` (Task 9).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_derivadas.py
import numpy as np
import pandas as pd
import pytest

from src.derivadas import (
    agregar_agregados_producto,
    agregar_banderas_faltantes,
    agregar_ratios_financieros,
    agregar_tendencia_relativa,
    agregar_vivienda_como_categoria,
    division_segura,
    resumen_cv_saldo_liquido,
)


def test_division_por_cero_devuelve_nulo_no_infinito():
    """SPEC_V2 §5: todas las divisiones manejan denominador cero devolviendo
    nulo, no infinito."""
    r = division_segura(pd.Series([10.0, 10.0, 0.0]), pd.Series([2.0, 0.0, 0.0]))
    assert r.iloc[0] == 5.0
    assert pd.isna(r.iloc[1])
    assert pd.isna(r.iloc[2])
    assert not np.isinf(r.to_numpy(dtype="float64", na_value=0.0)).any()


def test_division_por_nulo_devuelve_nulo():
    r = division_segura(pd.Series([10.0]), pd.Series([np.nan]))
    assert pd.isna(r.iloc[0])


def test_division_numerador_nulo_devuelve_nulo():
    r = division_segura(pd.Series([np.nan]), pd.Series([2.0]))
    assert pd.isna(r.iloc[0])


def test_division_segura_preserva_el_indice():
    num = pd.Series([10.0, 20.0], index=[7, 9])
    den = pd.Series([2.0, 0.0], index=[7, 9])
    r = division_segura(num, den)
    assert r.index.tolist() == [7, 9]


def test_division_segura_denominador_positivo_excluye_negativos():
    """D3/N2: tendencia_relativa_6m usa denominador_positivo=True. Con un
    saldo_prom_6m negativo (sobregiro) el signo del ratio se invierte y deja
    de significar "dirección del cambio", así que se descarta a nulo."""
    r = division_segura(pd.Series([10.0, 10.0]), pd.Series([2.0, -5.0]),
                        denominador_positivo=True)
    assert r.iloc[0] == 5.0
    assert pd.isna(r.iloc[1])


def _df_financiero():
    return pd.DataFrame({
        "ingresos_mensuales": [1000.0, 0.0, 2000.0],
        "total_egresos_mensuales": [400.0, 100.0, 500.0],
        "total_activos": [5000.0, 0.0, 8000.0],
        "total_pasivos": [1000.0, 50.0, 0.0],
        "total_patrimonio": [4000.0, 0.0, 8000.0],
        "capacidad_ahorro": [600.0, -100.0, 1500.0],
        "estimador_ingreso": [900.0, np.nan, 2500.0],
    })


def test_ratios_financieros_valores_y_ceros():
    r = agregar_ratios_financieros(_df_financiero())
    assert r.loc[0, "ratio_egreso_ingreso"] == 0.4
    assert r.loc[0, "pct_ahorro_ingreso"] == 0.6
    assert r.loc[0, "ratio_pasivo_activo"] == 0.2
    assert r.loc[0, "patrimonio_por_ingreso"] == 4000.0 / 12000.0
    # D10: la variable se llama dif_ingreso_declarado_estimado y su fórmula es
    # ingresos_mensuales - estimador_ingreso (el nombre ya no contradice la fórmula)
    assert r.loc[0, "dif_ingreso_declarado_estimado"] == 100.0
    assert r.loc[0, "pct_dif_ingreso"] == 0.1
    # cliente 1: ingresos 0 y activos 0 -> todos los ratios nulos, ninguno inf
    for col in ["ratio_egreso_ingreso", "pct_ahorro_ingreso",
                "ratio_pasivo_activo", "patrimonio_por_ingreso", "pct_dif_ingreso"]:
        assert pd.isna(r.loc[1, col]), col
    # cliente 2: activos 8000 y pasivos 0 -> 0.0, que es un valor legítimo
    assert r.loc[2, "ratio_pasivo_activo"] == 0.0
    # estimador nulo -> dif nulo, no 0
    assert pd.isna(r.loc[1, "dif_ingreso_declarado_estimado"])


def _df_productos():
    cols = {}
    for p in ["cuenta_ahorro", "cuenta_corriente", "bolsillos",
              "fiducuenta", "cdt", "inversion_virtual", "invesbot"]:
        cols[f"{p}_saldo_snapshot"] = [0.0, 0.0]
    df = pd.DataFrame(cols)
    df.loc[0, "cuenta_ahorro_saldo_snapshot"] = 100.0
    df.loc[0, "bolsillos_saldo_snapshot"] = 50.0
    df.loc[0, "cdt_saldo_snapshot"] = 700.0
    df.loc[0, "invesbot_saldo_snapshot"] = 9000.0
    df["total_patrimonio"] = [1000.0, 0.0]
    return df


def test_agregados_producto_distinguen_total_de_no_etiqueta():
    r = agregar_agregados_producto(_df_productos())
    assert r.loc[0, "saldo_liquido_total"] == 150.0     # ahorro + corriente + bolsillos
    assert r.loc[0, "n_productos_total"] == 4           # ahorro, bolsillos, cdt, invesbot
    assert r.loc[0, "n_productos_no_etiqueta"] == 3     # sin invesbot ni inv. virtual
    assert r.loc[0, "ratio_liquidez_patrimonio"] == 0.15
    assert pd.isna(r.loc[1, "ratio_liquidez_patrimonio"])   # patrimonio 0 -> nulo


def test_tendencia_relativa_por_producto():
    """D3: tendencia_relativa_6m = tendencia_6m / saldo_prom_6m, por producto."""
    df = pd.DataFrame({
        "cdt_tendencia_6m": [200.0, 50.0, 10.0],
        "cdt_saldo_prom_6m": [1000.0, 0.0, -20.0],
        "fiducuenta_tendencia_6m": [30.0],
        "fiducuenta_saldo_prom_6m": [300.0],
    }, index=[0, 1, 2]).reindex(columns=[
        "cdt_tendencia_6m", "cdt_saldo_prom_6m",
        "fiducuenta_tendencia_6m", "fiducuenta_saldo_prom_6m",
    ])
    df["fiducuenta_tendencia_6m"] = [30.0, 0.0, 0.0]
    df["fiducuenta_saldo_prom_6m"] = [300.0, 0.0, 0.0]
    r = agregar_tendencia_relativa(df)
    assert r.loc[0, "cdt_tendencia_relativa_6m"] == pytest.approx(0.2)
    assert pd.isna(r.loc[1, "cdt_tendencia_relativa_6m"])   # denominador 0
    assert pd.isna(r.loc[2, "cdt_tendencia_relativa_6m"])   # denominador negativo (N2)
    assert r.loc[0, "fiducuenta_tendencia_relativa_6m"] == pytest.approx(0.1)


def test_banderas_faltantes_por_bloque():
    df = pd.DataFrame({
        "ingresos_mensuales": [1.0, np.nan],
        "total_activos": [1.0, np.nan],
        "estimador_ingreso": [np.nan, 5.0],
    })
    r = agregar_banderas_faltantes(df, {
        "financiero": ["ingresos_mensuales", "total_activos"],
        "estimador": ["estimador_ingreso"],
    })
    assert r["falta_financiero"].tolist() == [0, 1]
    assert r["falta_estimador"].tolist() == [1, 0]


def test_vivienda_nulo_se_convierte_en_nivel_sin_dato():
    """SPEC_V2 §6.5: missing as a category, no imputación."""
    df = pd.DataFrame({"desc_tipo_de_vivienda": ["PROPIA", None, "ARRENDADA", np.nan]})
    r = agregar_vivienda_como_categoria(df)
    assert r["desc_tipo_de_vivienda"].tolist() == ["PROPIA", "Sin dato", "ARRENDADA", "Sin dato"]
    assert r["tiene_dato_vivienda"].tolist() == [1, 0, 1, 0]
    assert r["desc_tipo_de_vivienda"].isna().sum() == 0


FECHA_CORTE_TEST = pd.Timestamp("2026-06-01")
PRODUCTOS_LIQUIDOS_TEST = ["cuenta_ahorro", "cuenta_corriente", "bolsillos"]


def test_cv_saldo_liquido_coeficiente_de_variacion_sobre_ventana_fija():
    """D9: ventana fija de 6M desde fecha_corte, coeficiente de variación
    (std poblacional / media), no desviación absoluta."""
    panel = pd.DataFrame({
        "numero_id": [1] * 6,
        "producto": ["cuenta_ahorro"] * 6,
        "mes": pd.date_range("2025-12-01", periods=6, freq="MS"),
        "saldo_mes": [100.0, 100.0, 200.0, 200.0, 300.0, 300.0],
        "observado": [1, 0, 1, 0, 1, 0],   # 3 meses observados, cumple el mínimo
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    # media=200, std poblacional=sqrt(40000/6)=81.6497 -> cv=0.4082
    assert r.loc[1, "cv_saldo_liquido"] == pytest.approx(0.408248, rel=1e-4)
    assert r.loc[1, "cv_saldo_liquido_insuficiente"] == 0


def test_cv_saldo_liquido_nulo_si_menos_del_minimo_de_meses_observados():
    """D9: por debajo de 3 meses CON DATO (no arrastrado), nulo con bandera —
    nunca un valor calculado sobre muy pocos puntos."""
    panel = pd.DataFrame({
        "numero_id": [2] * 6,
        "producto": ["cuenta_ahorro"] * 6,
        "mes": pd.date_range("2025-12-01", periods=6, freq="MS"),
        "saldo_mes": [50.0] * 4 + [80.0, 80.0],
        "observado": [1, 0, 0, 0, 1, 0],   # solo 2 meses observados
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    assert pd.isna(r.loc[2, "cv_saldo_liquido"])
    assert r.loc[2, "cv_saldo_liquido_insuficiente"] == 1


def test_cv_saldo_liquido_nulo_si_media_no_es_positiva():
    """D9: manejar media cero (o negativa, sobregiro) devolviendo nulo."""
    panel = pd.DataFrame({
        "numero_id": [3] * 3,
        "producto": ["cuenta_corriente"] * 3,
        "mes": pd.date_range("2026-04-01", periods=3, freq="MS"),
        "saldo_mes": [-50.0, -50.0, -50.0],
        "observado": [1, 1, 1],
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    assert pd.isna(r.loc[3, "cv_saldo_liquido"])
    assert r.loc[3, "cv_saldo_liquido_insuficiente"] == 0   # sí hubo suficiente dato; el problema es la media


def test_cv_saldo_liquido_ignora_meses_fuera_de_la_ventana_de_6m():
    """La ventana es FIJA de 6 meses desde fecha_corte: un mes anterior a la
    ventana no debe influir en la media/std aunque esté en el panel."""
    panel = pd.DataFrame({
        "numero_id": [4] * 4,
        "producto": ["bolsillos"] * 4,
        "mes": pd.to_datetime(["2025-01-01", "2025-12-01", "2026-03-01", "2026-06-01"]),
        "saldo_mes": [999999.0, 100.0, 100.0, 100.0],   # el primer valor es de hace 17 meses
        "observado": [1, 1, 1, 1],
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    assert r.loc[4, "cv_saldo_liquido"] == pytest.approx(0.0)   # saldo plano DENTRO de la ventana


def test_cv_saldo_liquido_ignora_productos_no_liquidos():
    panel = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "mes": pd.to_datetime(["2026-04-01", "2026-05-01"]),
        "saldo_mes": [0.0, 100000.0],
        "observado": [1, 1],
    })
    r = resumen_cv_saldo_liquido(panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST)
    assert len(r) == 0
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_derivadas.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.derivadas'`

- [ ] **Step 3: Implementar `src/derivadas.py`**

```python
# src/derivadas.py
"""Variables derivadas de cliente_features (SPEC_V2 §5) y tratamiento de
`desc_tipo_de_vivienda` como categoría con nivel "Sin dato" (§6.5).

Regla transversal: toda división devuelve NaN cuando el denominador es 0 o nulo.
Un `inf` en una feature envenena cualquier modelo lineal y distorsiona los
percentiles de los modelos de árbol; un NaN es información honesta ("no se puede
calcular") que HistGradientBoosting maneja nativamente.
"""
import numpy as np
import pandas as pd

import config

ETIQUETA_SIN_DATO = "Sin dato"


def division_segura(numerador, denominador, denominador_positivo: bool = False) -> pd.Series:
    """División elemento a elemento; NaN (nunca inf) si el denominador es 0 o nulo.

    `denominador_positivo=True` también anula el resultado cuando el
    denominador es negativo (D3/N2: con un denominador negativo el signo del
    ratio se invierte y deja de significar lo que se quiere medir).
    """
    num = pd.Series(numerador).astype("float64")
    den = pd.Series(denominador).astype("float64")
    if denominador_positivo:
        den = den.mask(den <= 0)      # 0 o negativo -> NaN
    else:
        den = den.mask(den == 0)      # 0 -> NaN, y NaN/NaN = NaN
    return num / den


def agregar_ratios_financieros(df: pd.DataFrame) -> pd.DataFrame:
    """Los 6 ratios de capacidad financiera de SPEC_V2 §5."""
    out = df.copy()
    out["ratio_egreso_ingreso"] = division_segura(
        out["total_egresos_mensuales"], out["ingresos_mensuales"])
    out["pct_ahorro_ingreso"] = division_segura(
        out["capacidad_ahorro"], out["ingresos_mensuales"])
    out["ratio_pasivo_activo"] = division_segura(
        out["total_pasivos"], out["total_activos"])
    out["patrimonio_por_ingreso"] = division_segura(
        out["total_patrimonio"], out["ingresos_mensuales"] * 12)
    # D10: la variable se llama dif_ingreso_declarado_estimado (antes
    # gap_ingreso_estimado_declarado, un nombre que contradecía su propia
    # fórmula). Se conserva la fórmula del spec: declarado − estimado.
    out["dif_ingreso_declarado_estimado"] = (
        out["ingresos_mensuales"] - out["estimador_ingreso"])
    out["pct_dif_ingreso"] = division_segura(
        out["dif_ingreso_declarado_estimado"], out["ingresos_mensuales"])
    return out


def agregar_tendencia_relativa(df: pd.DataFrame) -> pd.DataFrame:
    """`{producto}_tendencia_relativa_6m` para cada producto (D3).

    tendencia_relativa = tendencia_6m / saldo_prom_6m. La tendencia en pesos
    absolutos no es comparable entre clientes de distinta escala patrimonial;
    el ratio sí. `denominador_positivo=True` (N2): con `saldo_prom_6m` <= 0 el
    ratio pierde sentido direccional, así que se descarta a nulo en vez de
    invertir el signo.
    """
    out = df.copy()
    for producto in config.PRODUCTOS:
        col_tend = f"{producto}_tendencia_6m"
        col_prom = f"{producto}_saldo_prom_6m"
        if col_tend not in out.columns or col_prom not in out.columns:
            continue
        out[f"{producto}_tendencia_relativa_6m"] = division_segura(
            out[col_tend], out[col_prom], denominador_positivo=True)
    return out


def agregar_agregados_producto(df: pd.DataFrame) -> pd.DataFrame:
    """Saldo líquido, conteos de producto y ratio de liquidez (SPEC_V2 §5).

    `n_productos_total` incluye Invesbot e Inversión Virtual, así que es
    DESCRIPTIVA, no predictora: está en la lista negra de `src/fuga.py`.
    """
    out = df.copy()
    cols_liquidos = [f"{p}_saldo_snapshot" for p in config.PRODUCTOS_LIQUIDOS]
    cols_todos = [f"{p}_saldo_snapshot" for p in config.PRODUCTOS]
    cols_no_etiqueta = [
        f"{p}_saldo_snapshot" for p in config.PRODUCTOS
        if p not in config.PRODUCTOS_ETIQUETA
    ]

    out["saldo_liquido_total"] = out[cols_liquidos].fillna(0.0).sum(axis=1)
    out["n_productos_total"] = (out[cols_todos].fillna(0.0) > 0).sum(axis=1).astype(int)
    out["n_productos_no_etiqueta"] = (
        (out[cols_no_etiqueta].fillna(0.0) > 0).sum(axis=1).astype(int))
    out["ratio_liquidez_patrimonio"] = division_segura(
        out["saldo_liquido_total"], out["total_patrimonio"])
    return out


def agregar_banderas_faltantes(df: pd.DataFrame, cols_por_bloque: dict) -> pd.DataFrame:
    """Una bandera `falta_<bloque>` por bloque de variables (SPEC_V2 §5).

    Vale 1 si TODAS las columnas del bloque están nulas: la bandera marca
    "el bloque no se capturó", no "falta un campo suelto".
    """
    out = df.copy()
    for bloque, cols in cols_por_bloque.items():
        presentes = [c for c in cols if c in out.columns]
        if not presentes:
            continue
        out[f"falta_{bloque}"] = out[presentes].isnull().all(axis=1).astype(int)
    return out


def agregar_vivienda_como_categoria(df: pd.DataFrame,
                                    etiqueta: str = ETIQUETA_SIN_DATO) -> pd.DataFrame:
    """Missing as a category para `desc_tipo_de_vivienda` (SPEC_V2 §6.5).

    Con ~68% de nulos, imputar fabricaría la mayoría de la columna y el modelo
    aprendería la imputación. El nulo pasa a ser un nivel más.
    """
    out = df.copy()
    col = "desc_tipo_de_vivienda"
    out["tiene_dato_vivienda"] = out[col].notna().astype(int)
    out[col] = out[col].astype(object).where(out[col].notna(), etiqueta)
    return out


def resumen_cv_saldo_liquido(panel_mensual: pd.DataFrame, productos_liquidos=None,
                             *, fecha_corte, meses_ventana: int | None = None,
                             meses_minimos: int | None = None) -> pd.DataFrame:
    """Coeficiente de variación del saldo líquido mensual por cliente (D9).

    D9 CAMBIA la propuesta provisional (desviación absoluta sobre todo el
    historial disponible) en tres puntos:
      1. Ventana FIJA de `meses_ventana` (por defecto `config.VENTANA_MESES_AGREGACION`)
         contada hacia atrás desde `fecha_corte` — no todo el historial. Clientes
         con historias de distinta longitud producían desviaciones no comparables.
      2. Mínimo de `meses_minimos` (por defecto `config.MESES_MINIMOS_CV_LIQUIDO`)
         meses con dato REAL (columna `observado` de `src/panel_mensual.py`, no
         arrastrado por forward fill). Por debajo, nulo con bandera
         `cv_saldo_liquido_insuficiente`, no un valor calculado sobre pocos puntos.
      3. Coeficiente de variación (std poblacional / media) en vez de la
         desviación absoluta, por la misma razón de escala que `tendencia_relativa`
         (D3). Media <= 0 -> nulo (sin bandera: hubo dato suficiente, el problema
         es la escala, no la cantidad de datos).
    """
    if productos_liquidos is None:
        productos_liquidos = config.PRODUCTOS_LIQUIDOS
    meses_ventana = meses_ventana or config.VENTANA_MESES_AGREGACION
    meses_minimos = meses_minimos or config.MESES_MINIMOS_CV_LIQUIDO
    fecha_corte = pd.Timestamp(fecha_corte)
    ventana_ini = fecha_corte - pd.DateOffset(months=meses_ventana)

    liquidos = panel_mensual[
        panel_mensual["producto"].isin(productos_liquidos)
        & (panel_mensual["mes"] >= ventana_ini)
        & (panel_mensual["mes"] <= fecha_corte)
    ]
    if liquidos.empty:
        return pd.DataFrame(columns=[
            "numero_id", "cv_saldo_liquido", "cv_saldo_liquido_insuficiente"])

    por_mes = (
        liquidos.groupby(["numero_id", "mes"], as_index=False)
        .agg(saldo_mes=("saldo_mes", "sum"), observado=("observado", "max"))
    )
    stats = (
        por_mes.groupby("numero_id", as_index=False)
        .agg(media=("saldo_mes", "mean"),
             std=("saldo_mes", lambda s: s.std(ddof=0)),
             n_meses_observados=("observado", "sum"))
    )

    stats["cv_saldo_liquido_insuficiente"] = (
        stats["n_meses_observados"] < meses_minimos).astype(int)
    media_valida = stats["media"] > 0
    stats["cv_saldo_liquido"] = np.where(
        (stats["cv_saldo_liquido_insuficiente"] == 0) & media_valida,
        stats["std"] / stats["media"],
        np.nan,
    )
    return stats[["numero_id", "cv_saldo_liquido", "cv_saldo_liquido_insuficiente"]]
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_derivadas.py -v
```
Expected: `15 passed`

- [ ] **Step 5: Commit**

```bash
git add src/derivadas.py tests/test_derivadas.py
git commit -m "✨feat: add derived variables incl. tendencia_relativa_6m and cv_saldo_liquido (SPEC_V2 5, 6.5, D3, D9, D10)"
```

---

## Task 9 [MODIFICA]: cablear las derivadas en `cliente_features`

**Files:**
- Modify: `oro/construir_cliente_features.py`
- Modify: `tests/test_construir_cliente_features.py`

**Interfaces:**
- Consumes: `src.derivadas.*`, `src.fecha_corte.calcular_fecha_corte` (Task 0B), tablas `saldos_mensual_plata` y `primer_registro_plata` (Task 7).
- Produces: `cliente_features` con las variables de SPEC_V2 §5 (menos `perfil_incompleto`, que llega en la Task 13 tras la verificación de §6.5.2). Añade `antiguedad_relacion_meses` (D8, contra `FECHA_CORTE` global), `cv_saldo_liquido` + `cv_saldo_liquido_insuficiente` (D9, reemplaza a `volatilidad_saldo_liquido`), `{producto}_tendencia_relativa_6m` por producto (D3), `dif_ingreso_declarado_estimado`/`pct_dif_ingreso` (D10), `tiene_dato_vivienda`, `falta_estimador`, `falta_financiero`, `falta_vivienda`.

- [ ] **Step 1: Unificar los fixtures de `clientes_plata` (evita romper las Tasks 2-3)**

A partir de esta tarea `construir_cliente_features` llama a `agregar_ratios_financieros`, que necesita las 5 columnas financieras + `capacidad_ahorro` + `desc_tipo_de_vivienda`. Los fixtures de las Tasks 2 y 3 solo traen `numero_id` y `sin_dato_financiero_total`, así que fallarían con `KeyError`. Añadir este helper al principio de `tests/test_construir_cliente_features.py` (justo debajo de `_tabla_producto`):

```python
def _clientes_plata(ids, **overrides):
    """Fixture de clientes_plata con TODAS las columnas que consume la capa oro.

    Valores por defecto neutros: financieros completos (no dispara ninguna
    bandera de faltante) y vivienda nula (para ejercitar el nivel "Sin dato").
    """
    n = len(ids)
    datos = {
        "numero_id": list(ids),
        "sin_dato_financiero": [False] * n,
        "sin_dato_financiero_total": [False] * n,
        "desc_segmento": ["PERSONAL"] * n,
        "grupo_edad": ["30-39"] * n,
        "desc_genero": ["F"] * n,
        "desc_tipo_de_vivienda": [None] * n,
        "ingresos_mensuales": [1000.0] * n,
        "total_egresos_mensuales": [400.0] * n,
        "total_activos": [5000.0] * n,
        "total_pasivos": [1000.0] * n,
        "total_patrimonio": [4000.0] * n,
        "capacidad_ahorro": [600.0] * n,
    }
    datos.update(overrides)
    return pd.DataFrame(datos)


def _plata_vacia_producto():
    return pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                 "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])


def _panel_y_primer_registro_vacios(plata_db):
    """saldos_mensual_plata y primer_registro_plata: insumos de volatilidad y antigüedad."""
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["numero_id", "producto", "mes", "saldo_mes"]),
        plata_db, "saldos_mensual_plata")
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["numero_id", "primer_mes"]),
        plata_db, "primer_registro_plata")
```

Después, en los tests de las Tasks 2 y 3, sustituir cada construcción manual de `clientes_plata` por `_clientes_plata([...], sin_dato_financiero_total=[...])`, cada `pd.DataFrame(columns=[...])` de producto por `_plata_vacia_producto()`, y añadir una llamada a `_panel_y_primer_registro_vacios(plata_db)` antes de `construir_cliente_features()`. Ejemplo para el test de la Task 2:

```python
    escribir_tabla_sqlite(_clientes_plata([301, 302]), plata_db, "clientes_plata")
    ...
    _panel_y_primer_registro_vacios(plata_db)
    r = construir_cliente_features().set_index("numero_id")
```

Y para el test de §2, donde los valores financieros sí importan:

```python
    escribir_tabla_sqlite(
        _clientes_plata([201, 202, 203, 204],
                        sin_dato_financiero_total=[False, False, True, True]),
        plata_db, "clientes_plata",
    )
```

- [ ] **Step 2: Escribir el test que falla**

Añadir a `tests/test_construir_cliente_features.py`:

```python
def test_cliente_features_incluye_las_derivadas_de_spec_v2(tmp_path, monkeypatch):
    """SPEC_V2 §5: las derivadas se calculan dentro de la capa oro, no en el notebook."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    escribir_tabla_sqlite(pd.DataFrame({
        "numero_id": [501],
        "sin_dato_financiero_total": [False],
        "desc_tipo_de_vivienda": [None],
        "ingresos_mensuales": [1000.0],
        "total_egresos_mensuales": [400.0],
        "total_activos": [5000.0],
        "total_pasivos": [1000.0],
        "total_patrimonio": [4000.0],
        "capacidad_ahorro": [600.0],
    }), plata_db, "clientes_plata")

    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    escribir_tabla_sqlite(pd.DataFrame([_tabla_producto(501, "cuenta_ahorro", saldo_snapshot=300.0)]),
                          plata_db, "aho_cte_plata")
    for t in ["bolsillos_plata", "fiducuenta_plata", "cdt_inversion_virtual_plata", "invesbot_plata"]:
        escribir_tabla_sqlite(vacia, plata_db, t)
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata")
    escribir_tabla_sqlite(pd.DataFrame({
        "numero_id": [501, 501, 501],
        "producto": ["cuenta_ahorro"] * 3,
        "mes": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "saldo_mes": [100.0, 200.0, 300.0],
        "observado": [1, 1, 1],
    }), plata_db, "saldos_mensual_plata")
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [501], "primer_mes": ["2026-01-01"]}),
        plata_db, "primer_registro_plata")

    # FECHA_CORTE se calcula desde bronce.db (Task 0B): el fixture de esta
    # tarea no escribe bronce, así que se monkeypatchea directamente.
    monkeypatch.setattr(
        "oro.construir_cliente_features.calcular_fecha_corte",
        lambda: pd.Timestamp("2026-03-01"))

    r = construir_cliente_features().set_index("numero_id")

    assert r.loc[501, "ratio_egreso_ingreso"] == 0.4
    assert r.loc[501, "saldo_liquido_total"] == 300.0
    assert r.loc[501, "n_productos_no_etiqueta"] == 1
    assert r.loc[501, "desc_tipo_de_vivienda"] == "Sin dato"
    assert r.loc[501, "tiene_dato_vivienda"] == 0
    assert r.loc[501, "falta_estimador"] == 1
    assert r.loc[501, "falta_financiero"] == 0
    # media=200, std poblacional=sqrt(20000/3)=81.6497 -> cv=0.4082 (D9)
    assert abs(r.loc[501, "cv_saldo_liquido"] - 0.408248) < 1e-4
    assert r.loc[501, "cv_saldo_liquido_insuficiente"] == 0
    assert r.loc[501, "antiguedad_relacion_meses"] == 2   # ene -> mar (FECHA_CORTE, D8)
    assert r.loc[501, "cuenta_ahorro_tendencia_relativa_6m"] == (
        r.loc[501, "cuenta_ahorro_tendencia_6m"] / r.loc[501, "cuenta_ahorro_saldo_prom_6m"])
```

- [ ] **Step 3: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_construir_cliente_features.py::test_cliente_features_incluye_las_derivadas_de_spec_v2 -v
```
Expected: FAIL con `KeyError: 'ratio_egreso_ingreso'`

- [ ] **Step 4: Implementar**

En `oro/construir_cliente_features.py`, añadir imports y el bloque de derivadas **después** del cálculo de `apto_entrenamiento` y **antes** de `escribir_tabla_sqlite`:

```python
import pandas as pd

from src.derivadas import (
    agregar_agregados_producto,
    agregar_banderas_faltantes,
    agregar_ratios_financieros,
    agregar_tendencia_relativa,
    agregar_vivienda_como_categoria,
    resumen_cv_saldo_liquido,
)
from src.fecha_corte import calcular_fecha_corte
```

```python
    # --- SPEC_V2 §5: variables derivadas ---
    base = agregar_ratios_financieros(base)
    base = agregar_agregados_producto(base)
    base = agregar_tendencia_relativa(base)   # D3: {producto}_tendencia_relativa_6m
    base = agregar_vivienda_como_categoria(base)
    base = agregar_banderas_faltantes(base, {
        "financiero": config.COLS_FINANCIERAS,
        "estimador": ["estimador_ingreso"],
    })
    # `falta_vivienda` NO sale de agregar_banderas_faltantes: `agregar_vivienda_como_categoria`
    # ya sustituyó los nulos por "Sin dato", así que la columna no tiene nulos que contar.
    # Es el complemento exacto de la bandera que esa función dejó.
    base["falta_vivienda"] = (1 - base["tiene_dato_vivienda"]).astype(int)

    # D4/D8: FECHA_CORTE global — misma referencia para la ventana de
    # cv_saldo_liquido y para la antigüedad de la relación.
    fecha_corte = calcular_fecha_corte()

    # D9: coeficiente de variación del saldo líquido, ventana fija de 6M desde
    # FECHA_CORTE, mínimo de meses observados (Task 7 ya regulariza todas las
    # fuentes contra ese mismo mes_max).
    panel = leer_tabla_sqlite(config.PLATA_DB, "saldos_mensual_plata")
    panel["mes"] = pd.to_datetime(panel["mes"])
    base = base.merge(
        resumen_cv_saldo_liquido(panel, config.PRODUCTOS_LIQUIDOS, fecha_corte=fecha_corte),
        on="numero_id", how="left",
    )
    base["cv_saldo_liquido_insuficiente"] = (
        base["cv_saldo_liquido_insuficiente"].fillna(1).astype(int))

    # D8: antigüedad de la relación = meses entre FECHA_CORTE global y el
    # primer registro del cliente en cualquier fuente (ya NO "mes máximo del
    # panel" como en el borrador anterior; con Task 7 corregida por D4 ambos
    # coinciden, pero se calcula explícitamente contra FECHA_CORTE por D8).
    primer = leer_tabla_sqlite(config.PLATA_DB, "primer_registro_plata")
    primer["primer_mes"] = pd.to_datetime(primer["primer_mes"])
    primer["antiguedad_relacion_meses"] = (
        (fecha_corte.year - primer["primer_mes"].dt.year) * 12
        + (fecha_corte.month - primer["primer_mes"].dt.month)
    ).astype("Int64")
    base = base.merge(
        primer[["numero_id", "antiguedad_relacion_meses"]], on="numero_id", how="left")
```

- [ ] **Step 5: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_construir_cliente_features.py -v
```
Expected: `4 passed` (los 3 de las Tasks 2-3, ya con los fixtures unificados, + el nuevo)

- [ ] **Step 6: Regenerar oro y verificar sobre datos reales**

```bash
python -m oro.construir_cliente_features
```
Expected: sin errores; `cliente_features` con más columnas que antes.

```bash
python -c "
import numpy as np
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
esperadas = ['ratio_egreso_ingreso','pct_ahorro_ingreso','ratio_pasivo_activo',
             'patrimonio_por_ingreso','dif_ingreso_declarado_estimado','pct_dif_ingreso',
             'saldo_liquido_total','ratio_liquidez_patrimonio','n_productos_total',
             'n_productos_no_etiqueta','antiguedad_relacion_meses',
             'cv_saldo_liquido','cv_saldo_liquido_insuficiente','tiene_dato_vivienda',
             'falta_estimador','falta_financiero','falta_vivienda']
esperadas += [f'{p}_tendencia_relativa_6m' for p in config.PRODUCTOS]
faltan = [c for c in esperadas if c not in df.columns]
assert not faltan, f'faltan columnas: {faltan}'
num = df.select_dtypes(include=[np.number])
infs = {c: int(np.isinf(num[c].to_numpy(dtype=float, na_value=0.0)).sum()) for c in num.columns}
con_inf = {c: n for c, n in infs.items() if n}
assert not con_inf, f'columnas con infinitos: {con_inf}'
assert df['desc_tipo_de_vivienda'].isna().sum() == 0
print(f'OK: {len(esperadas)} derivadas presentes, 0 infinitos, vivienda sin nulos')
print(df['desc_tipo_de_vivienda'].value_counts(dropna=False).to_string())
"
```
Expected: `OK: 23 derivadas presentes, 0 infinitos, vivienda sin nulos` (16 + 7 `{producto}_tendencia_relativa_6m`) + la distribución de vivienda con `Sin dato` como nivel mayoritario (~68%).

- [ ] **Step 7: Commit**

```bash
git add oro/construir_cliente_features.py tests/test_construir_cliente_features.py
git commit -m "✨feat: wire SPEC_V2 derived variables into gold cliente_features (D3, D4, D8, D9, D10)"
```

---

## Task 10 [NUEVO]: `src/log_decisiones.py` — registro de decisiones (SPEC_V2 §10)

**Files:**
- Create: `tests/test_log_decisiones.py`
- Create: `src/log_decisiones.py`

**Interfaces:**
- Produces: `registrar_decision(clave, decision, motivo, evidencia=None, ruta=None) -> Path` (append a `outputs/decisiones/log_decisiones.csv`; la última entrada por `clave` gana), `leer_log(ruta=None) -> pd.DataFrame`. Consumidas por notebooks 03, 04, 06, 07.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_log_decisiones.py
import pandas as pd

from src.log_decisiones import leer_log, registrar_decision


def test_registrar_crea_el_archivo_con_cabecera(tmp_path):
    ruta = tmp_path / "log.csv"
    registrar_decision("imputacion_estimador", "no_imputar",
                       "AUC=0.55 -> ausencia aleatoria y el modelo maneja nulos",
                       evidencia={"auc": 0.55}, ruta=ruta)
    df = leer_log(ruta)
    assert list(df.columns) == ["timestamp", "clave", "decision", "motivo", "evidencia"]
    assert df.loc[0, "clave"] == "imputacion_estimador"
    assert df.loc[0, "decision"] == "no_imputar"


def test_registrar_hace_append_y_conserva_el_historial(tmp_path):
    ruta = tmp_path / "log.csv"
    registrar_decision("vivienda", "conservar_categorica", "IV=0.031", ruta=ruta)
    registrar_decision("vivienda", "descartar", "IV recalculado=0.008", ruta=ruta)
    df = leer_log(ruta)
    assert len(df) == 2
    assert df.loc[1, "decision"] == "descartar"


def test_evidencia_se_serializa_como_json(tmp_path):
    import json
    ruta = tmp_path / "log.csv"
    registrar_decision("k", "d", "m", evidencia={"auc": 0.7, "n": 3}, ruta=ruta)
    df = leer_log(ruta)
    assert json.loads(df.loc[0, "evidencia"]) == {"auc": 0.7, "n": 3}


def test_evidencia_vacia_no_rompe(tmp_path):
    ruta = tmp_path / "log.csv"
    registrar_decision("k", "d", "m", ruta=ruta)
    df = leer_log(ruta)
    assert df.loc[0, "evidencia"] == "{}"


def test_leer_log_inexistente_devuelve_dataframe_vacio(tmp_path):
    df = leer_log(tmp_path / "no_existe.csv")
    assert df.empty
    assert list(df.columns) == ["timestamp", "clave", "decision", "motivo", "evidencia"]
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_log_decisiones.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.log_decisiones'`

- [ ] **Step 3: Implementar `src/log_decisiones.py`**

```python
# src/log_decisiones.py
"""Log de decisiones del pipeline (SPEC_V2 §10).

"Toda decisión de imputación debe quedar registrada en un log de decisiones."
Se registra en CSV append-only: cada fila es una decisión tomada, con la
evidencia numérica que la justificó. Si una decisión se revisa, se añade una
fila nueva en vez de sobrescribir — el historial es parte del entregable.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config

COLUMNAS = ["timestamp", "clave", "decision", "motivo", "evidencia"]


def _ruta_por_defecto() -> Path:
    return config.OUTPUTS_DIR / "decisiones" / "log_decisiones.csv"


def registrar_decision(clave: str, decision: str, motivo: str,
                       evidencia: dict | None = None, ruta: Path | None = None) -> Path:
    ruta = Path(ruta) if ruta is not None else _ruta_por_defecto()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fila = pd.DataFrame([{
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "clave": clave,
        "decision": decision,
        "motivo": motivo,
        "evidencia": json.dumps(evidencia or {}, ensure_ascii=False, default=str),
    }], columns=COLUMNAS)
    fila.to_csv(ruta, mode="a", header=not ruta.exists(), index=False, encoding="utf-8")
    return ruta


def leer_log(ruta: Path | None = None) -> pd.DataFrame:
    ruta = Path(ruta) if ruta is not None else _ruta_por_defecto()
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS)
    return pd.read_csv(ruta, encoding="utf-8")
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_log_decisiones.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/log_decisiones.py tests/test_log_decisiones.py
git commit -m "✨feat: add append-only decision log (SPEC_V2 10)"
```

---

## Task 11 [MODIFICA]: verificaciones de granularidad (SPEC_V2 §9)

**Files:**
- Create: `tests/test_granularidad.py`
- Modify: `bronce/diagnostico_calidad.py`

**Interfaces:**
- Produces: `verificar_unicidad_producto_fecha(df, nombre) -> dict`, `verificar_unicidad_cliente(df, nombre) -> dict` en `bronce/diagnostico_calidad.py`; secciones nuevas en `outputs/quality/reporte_calidad.md`. Los tests de `tests/test_granularidad.py` corren contra las bases reales y se **saltan** si no existen.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_granularidad.py
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


def test_verificar_unicidad_cliente():
    assert verificar_unicidad_cliente(pd.DataFrame({"numero_id": [1, 2]}), "t")["unico"] is True
    assert verificar_unicidad_cliente(pd.DataFrame({"numero_id": [1, 1]}), "t")["unico"] is False


@pytest.mark.skipif(not config.BRONCE_DB.exists(), reason="bronce.db no construido")
@pytest.mark.parametrize("tabla", TABLAS_SALDO)
def test_bronce_unico_por_cliente_producto_fecha(tabla):
    """SPEC_V2 §9.1"""
    r = verificar_unicidad_producto_fecha(leer_tabla_sqlite(config.BRONCE_DB, tabla), tabla)
    assert r["unico"], f"{tabla}: {r['duplicados']} combinaciones (id, producto, fecha) repetidas"


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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_granularidad.py -v
```
Expected: FAIL con `ImportError: cannot import name 'verificar_unicidad_producto_fecha'`

- [ ] **Step 3: Implementar en `bronce/diagnostico_calidad.py`**

Añadir las dos funciones y su reporte:

```python
def verificar_unicidad_producto_fecha(df, nombre_tabla):
    """SPEC_V2 §9.1: (numero_id, producto, fecha) debe ser único."""
    claves = ["numero_id", "producto", "fecha"]
    presentes = [c for c in claves if c in df.columns]
    if len(presentes) < 3:
        return {"tabla": nombre_tabla, "duplicados": 0, "unico": True,
                "nota": f"columnas ausentes: {set(claves) - set(presentes)}"}
    dup = int(df.duplicated(subset=claves).sum())
    return {"tabla": nombre_tabla, "duplicados": dup, "unico": dup == 0}


def verificar_unicidad_cliente(df, nombre_tabla):
    """SPEC_V2 §9.2: numero_id único."""
    dup = int(df["numero_id"].duplicated().sum())
    return {"tabla": nombre_tabla, "duplicados": dup, "unico": dup == 0}


def reporte_granularidad(resultados):
    lineas = ["## Granularidad (SPEC_V2 §9)"]
    for r in resultados:
        estado = "OK" if r["unico"] else f"FALLA ({r['duplicados']} duplicados)"
        lineas.append(f"- {r['tabla']}: {estado}")
    return lineas
```

Y en `main()`, dentro del bucle sobre `TABLAS_SALDO`, acumular resultados y añadirlos al reporte:

```python
def main():
    clientes = leer_tabla_sqlite(config.BRONCE_DB, "clientes")
    ids_clientes = set(clientes["numero_id"].unique())

    lineas = ["# Reporte de calidad — bronce", ""]
    lineas += reporte_nulos_clientes(clientes)
    lineas += reporte_duplicados_clientes(clientes)

    granularidad = []
    for tabla in TABLAS_SALDO:
        df = leer_tabla_sqlite(config.BRONCE_DB, tabla)
        lineas += reporte_encoding_producto(tabla, df)
        lineas += reporte_integridad_referencial(tabla, df, ids_clientes)
        granularidad.append(verificar_unicidad_producto_fecha(df, tabla))

    estimador = leer_tabla_sqlite(config.BRONCE_DB, "estimador_ing")
    lineas += reporte_integridad_referencial("estimador_ing", estimador, ids_clientes)
    granularidad.append(verificar_unicidad_cliente(estimador, "estimador_ing"))

    if config.ORO_DB.exists():
        cf = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
        granularidad.append(verificar_unicidad_cliente(cf, "cliente_features"))

    lineas += reporte_granularidad(granularidad)

    salida = config.OUTPUTS_DIR / "quality" / "reporte_calidad.md"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Reporte escrito en {salida}")
    for r in granularidad:
        print(f"  {r['tabla']}: {'OK' if r['unico'] else 'DUPLICADOS=' + str(r['duplicados'])}")
```

- [ ] **Step 4: Ejecutar los tests**

```bash
python -m pytest tests/test_granularidad.py -v
```
Expected: `3 passed` unitarios + los paramétricos contra datos reales. **Si alguno de los `test_bronce_unico_por_cliente_producto_fecha` falla, es un hallazgo real de SPEC_V2 §9.1: anotarlo y reportarlo antes de seguir** (afecta la validez de `agregar_serie_saldo`).

- [ ] **Step 5: Regenerar el reporte**

```bash
python bronce/diagnostico_calidad.py
```
Expected: `Reporte escrito en ...reporte_calidad.md` + una línea por tabla con `OK` o `DUPLICADOS=N`.

- [ ] **Step 6: Commit**

```bash
git add bronce/diagnostico_calidad.py tests/test_granularidad.py
git commit -m "✨feat: add granularity verifications for bronze/silver/gold (SPEC_V2 9)"
```

---

# FASE 3 — EDA de valores faltantes (SPEC_V2 §3)

> **Punto clave del spec:** la acción sobre `falta_estimador` **no se elige de antemano**, se deriva del AUC del clasificador auxiliar. Por eso la tabla de decisión vive en `src/decisiones.py` (código testeado) y el notebook solo la invoca con el AUC medido.

---

## Task 12 [NUEVO]: `src/decisiones.py` — tablas de decisión automáticas (SPEC_V2 §3.2, §6.5)

**Files:**
- Create: `tests/test_decisiones.py`
- Create: `src/decisiones.py`

**Interfaces:**
- Consumes: `config.UMBRAL_AUC_PATRON_DEBIL`, `UMBRAL_AUC_PATRON_INFORMATIVO`, `UMBRAL_IV_MINIMO`, `UMBRAL_LIFT_PERFIL_INCOMPLETO`, `UMBRAL_AUC_PROXY_MODERADO`, `UMBRAL_AUC_PROXY_SUSTANCIAL`.
- Produces:
  - `decidir_tratamiento_faltante_estimador(auc: float, modelo_maneja_nulos: bool = True) -> dict` con claves `auc, conclusion, accion, imputar, documentar_variables_asociadas, bandera_como_predictora`.
  - `decidir_tratamiento_vivienda(iv_categorica: float, iv_bandera: float) -> dict` con claves `accion, conservar_categorica, conservar_bandera, iv_categorica, iv_bandera`.
  - `lift_condicional(sin_a: set, sin_b: set, universo: set) -> float` — D7, reemplaza al índice de Jaccard (inaplicable: conjuntos desbalanceados, ver DECISIONES.md D7).
  - `decidir_perfil_incompleto(lift: float) -> dict` con claves `crear_bandera_unica, lift, umbral`.
  - `decidir_interpretacion_proxy_genero(auc: float) -> dict` con claves `auc, interpretacion, accion` — D6, bandas de interpretación en vez de umbral único.
  - Acciones posibles de `decidir_tratamiento_faltante_estimador`: `"conservar_bandera_sin_imputar"`, `"conservar_bandera_e_imputar_mediana_segmento"`, `"bandera_predictora_sin_imputacion_global"`.
  - Consumidas por `notebooks/03_eda_faltantes.ipynb` (Task 13), `notebooks/04_validacion_variables.ipynb` (Task 17) y `notebooks/07_auditoria_sesgo.ipynb` (Task 22).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_decisiones.py
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_decisiones.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.decisiones'`

- [ ] **Step 3: Implementar `src/decisiones.py`**

```python
# src/decisiones.py
"""Tablas de decisión de SPEC_V2, implementadas como código testeable.

La acción NO se elige de antemano: se deriva del estadístico medido (AUC del
clasificador auxiliar en §3.2, IV en §6.5). Tener la tabla en código y no en el
notebook evita que la decisión se "razone" a posteriori para justificar lo que
ya se hizo.

Bordes: SPEC_V2 §3.2 define las bandas como "< 0.60", "0.60 – 0.70" y "> 0.70".
Los valores exactos 0.60 y 0.70 caen por tanto en la banda intermedia.
"""
import config


def decidir_tratamiento_faltante_estimador(auc: float,
                                           modelo_maneja_nulos: bool = True) -> dict:
    """SPEC_V2 §3.2 — tabla de decisión sobre `falta_estimador`."""
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"AUC fuera de rango: {auc}")

    if auc < config.UMBRAL_AUC_PATRON_DEBIL:
        conclusion = "ausencia aproximadamente aleatoria"
        documentar = False
        bandera_predictora = False
    elif auc <= config.UMBRAL_AUC_PATRON_INFORMATIVO:
        conclusion = "patrón débil"
        documentar = True
        bandera_predictora = False
    else:
        conclusion = "ausencia informativa"
        documentar = True
        bandera_predictora = True

    if bandera_predictora:
        # §3.2, fila >0.70: NO imputar con medida central global. La bandera pasa
        # a ser predictora de pleno derecho; el valor queda nulo (o se imputa por
        # mediana condicional al grupo, decisión que toma el notebook con el grupo
        # identificado por las variables más importantes).
        accion = "bandera_predictora_sin_imputacion_global"
        imputar = False
    elif modelo_maneja_nulos:
        accion = "conservar_bandera_sin_imputar"
        imputar = False
    else:
        accion = "conservar_bandera_e_imputar_mediana_segmento"
        imputar = True

    return {
        "auc": float(auc),
        "conclusion": conclusion,
        "accion": accion,
        "imputar": imputar,
        "bandera_como_predictora": bandera_predictora,
        "documentar_variables_asociadas": documentar,
    }


def decidir_tratamiento_vivienda(iv_categorica: float, iv_bandera: float,
                                 umbral: float | None = None) -> dict:
    """SPEC_V2 §6.5 — regla de decisión de `desc_tipo_de_vivienda`."""
    umbral = config.UMBRAL_IV_MINIMO if umbral is None else umbral

    if iv_categorica >= umbral:
        accion, cat, band = "conservar_categorica_con_sin_dato", True, False
    elif iv_bandera >= umbral:
        accion, cat, band = "descartar_categorica_conservar_bandera", False, True
    else:
        accion, cat, band = "descartar_por_completo", False, False

    return {
        "accion": accion,
        "conservar_categorica": cat,
        "conservar_bandera": band,
        "iv_categorica": float(iv_categorica),
        "iv_bandera": float(iv_bandera),
        "umbral": float(umbral),
    }


def lift_condicional(sin_a, sin_b, universo) -> float:
    """D7 — reemplaza al índice de Jaccard, inaplicable aquí.

    Con conjuntos tan desbalanceados como "sin estimador_ingreso" (~114.431) y
    "sin desc_tipo_de_vivienda" (~585.000, 68% de la base), el Jaccard máximo
    alcanzable por construcción es ~0.196 (contención perfecta del menor en el
    mayor); un umbral de 0.50 nunca se activaría. El lift condicional no
    depende de los tamaños relativos:

        lift = P(sin_b | sin_a) / P(sin_b | con_a)

    lift > 1 -> faltar el bloque A predice faltar el bloque B (causa común de
    incompletitud). lift ~= 1 -> las ausencias son independientes.
    """
    a, b, u = set(sin_a), set(sin_b), set(universo)
    con_a = u - a
    if not a or not con_a:
        return float("nan")   # no se puede condicionar sobre un grupo vacío

    p_sin_a = len(a & b) / len(a)
    p_con_a = len(con_a & b) / len(con_a)
    if p_con_a == 0:
        return 0.0 if p_sin_a == 0 else float("inf")
    return p_sin_a / p_con_a


def decidir_perfil_incompleto(lift: float, umbral: float | None = None) -> dict:
    """SPEC_V2 §5 y §6.5.2 — una sola bandera `perfil_incompleto` en vez de
    banderas separadas, si los bloques de datos faltantes tienen causa común
    (D7: medida con lift condicional, umbral 1.5)."""
    umbral = config.UMBRAL_LIFT_PERFIL_INCOMPLETO if umbral is None else umbral
    return {
        "crear_bandera_unica": bool(lift >= umbral),
        "lift": float(lift),
        "umbral": float(umbral),
    }


def decidir_interpretacion_proxy_genero(auc: float) -> dict:
    """SPEC_V2 §6.6.1 — bandas de interpretación del AUC del clasificador de
    proxy de género (D6, reemplaza al umbral único de la propuesta provisional:
    un umbral binario oculta el caso intermedio, que es el resultado más
    probable y el que más requiere documentación explícita)."""
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"AUC fuera de rango: {auc}")

    if auc < config.UMBRAL_AUC_PROXY_MODERADO:
        interpretacion, accion = "proxy mínimo", "documentar_y_continuar"
    elif auc <= config.UMBRAL_AUC_PROXY_SUSTANCIAL:
        interpretacion, accion = "proxy moderado", "documentar_variables_asociadas"
    else:
        interpretacion, accion = "proxy sustancial", "investigar_mitigacion"

    return {"auc": float(auc), "interpretacion": interpretacion, "accion": accion}
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_decisiones.py -v
```
Expected: `23 passed`

- [ ] **Step 5: Commit**

```bash
git add src/decisiones.py tests/test_decisiones.py
git commit -m "✨feat: add SPEC_V2 conditional decision tables incl. lift condicional and proxy bands (3.2, 6.5, D6, D7)"
```

---

## Task 13 [NUEVO]: `notebooks/03_eda_faltantes.ipynb` (SPEC_V2 §3)

Notebook — **verificación de salida, no TDD.** Toda la lógica de decisión ya está testeada en la Task 12.

**Files:**
- Create: `notebooks/03_eda_faltantes.ipynb`

**Interfaces:**
- Consumes: `cliente_features` (Task 9), `src.decisiones.*`, `src.log_decisiones.registrar_decision`, `src.features_modelo.features_modelo_a`.
- Produces:
  - `outputs/eda/faltantes_solapamiento.json` — `{n_sin_estimador, n_nulos_financieros, n_interseccion, lift_estimador_vivienda, decision_perfil_incompleto}`
  - `outputs/eda/faltantes_deteccion_patron.json` — `{auc, conclusion, accion, imputar, top_10_variables}`
  - `outputs/eda/faltantes_tasa_adopcion.csv` — comparación de tasas + chi-cuadrado
  - Fila en `outputs/decisiones/log_decisiones.csv` con clave `tratamiento_falta_estimador`.

- [ ] **Step 1: Crear el notebook — celda 0 (§3.1 Solapamiento)**

```python
import json
import sys
sys.path.insert(0, "..")

import numpy as np
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite
from src.decisiones import decidir_perfil_incompleto, lift_condicional

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
(config.OUTPUTS_DIR / "eda").mkdir(parents=True, exist_ok=True)

universo = set(df["numero_id"])
sin_estimador = set(df.loc[df["falta_estimador"] == 1, "numero_id"])
# "nulos en las 5 columnas financieras": se reporta la lectura conservadora
# (algún nulo) y la estricta (los 5), porque las dos aparecen en el spec.
nulos_fin_any = set(df.loc[df[config.COLS_FINANCIERAS].isnull().any(axis=1), "numero_id"])
nulos_fin_all = set(df.loc[df[config.COLS_FINANCIERAS].isnull().all(axis=1), "numero_id"])
sin_vivienda = set(df.loc[df["tiene_dato_vivienda"] == 0, "numero_id"])

interseccion = sin_estimador & nulos_fin_any
# D7: el Jaccard es inaplicable (conjuntos desbalanceados, máximo alcanzable
# ~0.196 — ver DECISIONES.md). Se usa lift condicional en su lugar.
lift_est_viv = lift_condicional(sin_estimador, sin_vivienda, universo)
decision_perfil = decidir_perfil_incompleto(lift_est_viv)

solapamiento = {
    "n_total": int(len(df)),
    "n_sin_estimador": len(sin_estimador),
    "n_nulos_financieros_any": len(nulos_fin_any),
    "n_nulos_financieros_all": len(nulos_fin_all),
    "n_interseccion_estimador_financieros": len(interseccion),
    "n_sin_vivienda": len(sin_vivienda),
    "lift_estimador_vivienda": lift_est_viv,
    "decision_perfil_incompleto": decision_perfil,
}
with open(config.OUTPUTS_DIR / "eda" / "faltantes_solapamiento.json", "w",
          encoding="utf-8") as f:
    json.dump(solapamiento, f, indent=2, ensure_ascii=False)

print(json.dumps(solapamiento, indent=2, ensure_ascii=False))
print(f"\n% de la base sin estimador: {len(sin_estimador)/len(df):.1%}")
```

- [ ] **Step 2: Celda 1 (§3.2 Detección de patrón — clasificador auxiliar)**

```python
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from src.decisiones import decidir_tratamiento_faltante_estimador
from src.features_modelo import features_modelo_a
from src.log_decisiones import registrar_decision

# Objetivo auxiliar: ¿se puede predecir QUIÉN no tiene estimador de ingreso?
y_falta = df["falta_estimador"]

# Predictoras: el resto de variables disponibles (financieras, de producto,
# demográficas). Se quitan el propio estimador y sus banderas, que serían
# tautológicas, y se pasa por el guard anti-fuga por higiene.
excluir = {"estimador_ingreso", "tiene_estimador_ingreso", "falta_estimador"}
cols_aux = [c for c in features_modelo_a(df.columns) if c not in excluir]
X_aux = pd.get_dummies(
    df[cols_aux],
    columns=[c for c in ["desc_segmento", "grupo_edad", "desc_tipo_de_vivienda"]
             if c in cols_aux],
    dummy_na=False,
)

Xa_tr, Xa_te, ya_tr, ya_te = train_test_split(
    X_aux, y_falta, test_size=config.TEST_SIZE,
    random_state=config.RANDOM_STATE, stratify=y_falta,
)
aux = HistGradientBoostingClassifier(random_state=config.RANDOM_STATE)
aux.fit(Xa_tr, ya_tr)
auc_falta = float(roc_auc_score(ya_te, aux.predict_proba(Xa_te)[:, 1]))

# Top-10 variables por permutation importance (más confiable que la nativa).
# Se calcula sobre una submuestra del test para que el coste sea razonable.
sub = Xa_te.sample(n=min(30_000, len(Xa_te)), random_state=config.RANDOM_STATE)
pi = permutation_importance(
    aux, sub, ya_te.loc[sub.index], n_repeats=5,
    random_state=config.RANDOM_STATE, scoring="roc_auc",
)
top10 = (
    pd.DataFrame({"variable": sub.columns, "importancia": pi.importances_mean})
    .sort_values("importancia", ascending=False)
    .head(10)
    .reset_index(drop=True)
)

# HistGradientBoostingClassifier maneja NaN nativamente (Global Constraints)
decision = decidir_tratamiento_faltante_estimador(auc_falta, modelo_maneja_nulos=True)

print(f"AUC del clasificador auxiliar: {auc_falta:.4f}")
print(f"Conclusión: {decision['conclusion']}")
print(f"Acción a implementar: {decision['accion']}")
print("\nTop 10 variables asociadas a la ausencia del estimador:")
print(top10.to_string(index=False))

resultado_patron = {**decision, "top_10_variables": top10.to_dict(orient="records")}
with open(config.OUTPUTS_DIR / "eda" / "faltantes_deteccion_patron.json", "w",
          encoding="utf-8") as f:
    json.dump(resultado_patron, f, indent=2, ensure_ascii=False)

registrar_decision(
    clave="tratamiento_falta_estimador",
    decision=decision["accion"],
    motivo=f"AUC del clasificador auxiliar = {auc_falta:.4f} -> {decision['conclusion']} "
           f"(SPEC_V2 §3.2). Modelo final maneja nulos nativamente.",
    evidencia={"auc": auc_falta,
               "top_10": top10["variable"].tolist(),
               "n_sin_estimador": len(sin_estimador)},
)
```

- [ ] **Step 3: Celda 2 — aplicar la acción decidida**

```python
# La acción NO se elige aquí: viene de la tabla de decisión de §3.2 ya evaluada.
if decision["accion"] == "conservar_bandera_sin_imputar":
    print("ACCIÓN: se conserva `falta_estimador` y `estimador_ingreso` queda NULO. "
          "El modelo final (HistGradientBoosting) maneja el nulo nativamente.")
    imputacion = None

elif decision["accion"] == "conservar_bandera_e_imputar_mediana_segmento":
    medianas = df.groupby("desc_segmento")["estimador_ingreso"].median()
    print("ACCIÓN: imputación por mediana de `desc_segmento`.")
    print(medianas.to_string())
    imputacion = {"tipo": "mediana_por_desc_segmento",
                  "valores": {str(k): float(v) for k, v in medianas.dropna().items()}}

else:  # "bandera_predictora_sin_imputacion_global"
    # §3.2, fila >0.70: la bandera es predictora de pleno derecho. NO se imputa
    # con medida central global. Se ofrece la mediana condicional al grupo que
    # las variables más importantes identificaron.
    grupo = top10.loc[0, "variable"]
    print(f"ACCIÓN: `falta_estimador` pasa a predictora de pleno derecho. "
          f"Sin imputación global. Grupo condicional sugerido por la variable "
          f"más asociada: {grupo}.")
    if "desc_segmento" in df.columns:
        medianas = df.groupby("desc_segmento")["estimador_ingreso"].median()
        print("Medianas condicionales disponibles por desc_segmento:")
        print(medianas.to_string())
    imputacion = {"tipo": "sin_imputacion_global", "grupo_sugerido": str(grupo)}

print(f"\nRegistro de imputación: {imputacion}")
```

- [ ] **Step 4: Celda 3 (§3.3 Comparación de tasa de adopción + chi-cuadrado)**

```python
from scipy.stats import chi2_contingency

tabla = pd.crosstab(df["falta_estimador"], df["etiqueta_adopcion"])
chi2, p, gl, _ = chi2_contingency(tabla)

tasas = (
    df.groupby("falta_estimador")["etiqueta_adopcion"]
    .agg(n_clientes="count", n_adoptadores="sum", tasa_adopcion="mean")
    .reset_index()
)
tasas["grupo"] = tasas["falta_estimador"].map({0: "con estimador", 1: "sin estimador"})
dif = float(tasas.loc[tasas["falta_estimador"] == 1, "tasa_adopcion"].iloc[0]
            - tasas.loc[tasas["falta_estimador"] == 0, "tasa_adopcion"].iloc[0])

tasas["diferencia_vs_con_estimador"] = dif
tasas["chi2"] = float(chi2)
tasas["p_valor"] = float(p)
tasas["gl"] = int(gl)
tasas.to_csv(config.OUTPUTS_DIR / "eda" / "faltantes_tasa_adopcion.csv", index=False)

print(tasas.to_string(index=False))
print(f"\nDiferencia de tasa (sin − con): {dif:+.4%}")
print(f"Chi-cuadrado = {chi2:.2f}, gl = {gl}, p = {p:.3e}")
print(
    "\nSPEC_V2 §3.4 — RESTRICCIÓN: no se elimina ningún cliente por falta de "
    f"estimador de ingresos. Son {len(sin_estimador):,} clientes "
    f"({len(sin_estimador)/len(df):.1%} de la base) y probablemente concentran el "
    "perfil de adquisición en frío."
)
```

- [ ] **Step 5: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/03_eda_faltantes.ipynb
```
Expected: exit code 0.

- [ ] **Step 6: Verificar las salidas**

```bash
python -c "
import json
import pandas as pd
import config
from src.decisiones import decidir_tratamiento_faltante_estimador

with open(config.OUTPUTS_DIR / 'eda' / 'faltantes_solapamiento.json', encoding='utf-8') as f:
    s = json.load(f)
assert s['n_sin_estimador'] > 100_000, s
assert 0 <= s['n_interseccion_estimador_financieros'] <= min(
    s['n_sin_estimador'], s['n_nulos_financieros_any'])

with open(config.OUTPUTS_DIR / 'eda' / 'faltantes_deteccion_patron.json', encoding='utf-8') as f:
    p = json.load(f)
assert 0.0 <= p['auc'] <= 1.0
assert len(p['top_10_variables']) == 10
# la acción registrada debe ser EXACTAMENTE la que dicta la tabla para ese AUC
assert p['accion'] == decidir_tratamiento_faltante_estimador(p['auc'])['accion'], (
    'la accion aplicada no coincide con la tabla de decision de SPEC_V2 3.2')

t = pd.read_csv(config.OUTPUTS_DIR / 'eda' / 'faltantes_tasa_adopcion.csv')
assert set(t['falta_estimador']) == {0, 1}
assert t['tasa_adopcion'].between(0, 1).all()

log = pd.read_csv(config.OUTPUTS_DIR / 'decisiones' / 'log_decisiones.csv')
assert (log['clave'] == 'tratamiento_falta_estimador').any()

print(f'OK §3 — AUC={p[\"auc\"]:.4f} -> {p[\"conclusion\"]} -> {p[\"accion\"]}')
print(f'   sin estimador: {s[\"n_sin_estimador\"]:,} | intersección con nulos financieros: {s[\"n_interseccion_estimador_financieros\"]:,}')
"
```
Expected: `OK §3 — AUC=0.xxxx -> <conclusión> -> <acción>` y la línea de conteos.

- [ ] **Step 7: Verificar que NO se eliminó ningún cliente (§3.4)**

```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
assert len(df) == 860223, f'se perdieron clientes: {len(df)}'
print('OK §3.4: la base sigue completa, ningún cliente eliminado por falta de estimador')
"
```
Expected: `OK §3.4: la base sigue completa, ningún cliente eliminado por falta de estimador`

- [ ] **Step 8: Commit**

```bash
git add notebooks/03_eda_faltantes.ipynb
git commit -m "✨feat: add missing-value EDA notebook with AUC-driven decision table (SPEC_V2 3)"
```

---

# FASE 4 — Validación estadística de variables (SPEC_V2 §4, §6.5)

---

## Task 14 [MODIFICA]: `perfil_incompleto` condicional (SPEC_V2 §5, §6.5.2)

SPEC_V2 §5 dice que `perfil_incompleto` se crea **"solo si la verificación de la sección 6.5 confirma solapamiento alto"**. Esa verificación la produjo la Task 13.

**Files:**
- Modify: `oro/construir_cliente_features.py`
- Modify: `tests/test_construir_cliente_features.py`

**Interfaces:**
- Consumes: `outputs/eda/faltantes_solapamiento.json` (Task 13), `src.decisiones.decidir_perfil_incompleto`.
- Produces: columna `perfil_incompleto: int` en `cliente_features` **solo si** el lift condicional (D7) supera el umbral; si no, no se crea (las banderas por bloque de la Task 9 siguen siendo la señal).

- [ ] **Step 1: Escribir el test que falla**

```python
def test_perfil_incompleto_solo_si_hay_solapamiento_alto(tmp_path, monkeypatch):
    """SPEC_V2 §5: `perfil_incompleto` es una bandera única que reemplaza a las
    banderas por bloque, y solo se crea si el lift condicional (D7) lo justifica."""
    from oro.construir_cliente_features import agregar_perfil_incompleto

    df = pd.DataFrame({
        "numero_id": [1, 2, 3],
        "falta_estimador": [1, 1, 0],
        "falta_vivienda": [1, 0, 0],
    })

    alto = agregar_perfil_incompleto(df, lift_medido=2.4)
    assert "perfil_incompleto" in alto.columns
    assert alto["perfil_incompleto"].tolist() == [1, 1, 0]   # falta algún bloque

    bajo = agregar_perfil_incompleto(df, lift_medido=1.05)
    assert "perfil_incompleto" not in bajo.columns
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_construir_cliente_features.py::test_perfil_incompleto_solo_si_hay_solapamiento_alto -v
```
Expected: FAIL con `ImportError: cannot import name 'agregar_perfil_incompleto'`

- [ ] **Step 3: Implementar**

En `oro/construir_cliente_features.py`:

```python
import json

from src.decisiones import decidir_perfil_incompleto

BLOQUES_PERFIL = ["falta_estimador", "falta_vivienda", "falta_financiero"]


def _lift_medido_desde_eda():
    """Lee el lift condicional (D7) medido por notebooks/03_eda_faltantes.ipynb.
    Si el notebook aún no se ha ejecutado, devuelve None: la bandera no se crea
    y las banderas por bloque siguen siendo la señal disponible."""
    ruta = config.OUTPUTS_DIR / "eda" / "faltantes_solapamiento.json"
    if not ruta.exists():
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f).get("lift_estimador_vivienda")


def agregar_perfil_incompleto(df, lift_medido=None):
    """SPEC_V2 §5: bandera única, SOLO si §6.5.2 confirma causa común (D7: lift
    condicional >= config.UMBRAL_LIFT_PERFIL_INCOMPLETO)."""
    if lift_medido is None:
        lift_medido = _lift_medido_desde_eda()
    if lift_medido is None:
        return df
    if not decidir_perfil_incompleto(lift_medido)["crear_bandera_unica"]:
        return df

    out = df.copy()
    presentes = [c for c in BLOQUES_PERFIL if c in out.columns]
    out["perfil_incompleto"] = (out[presentes].sum(axis=1) > 0).astype(int)
    return out
```

Y llamarla justo antes de `escribir_tabla_sqlite` en `construir_cliente_features()`:

```python
    base = agregar_perfil_incompleto(base)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_construir_cliente_features.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Regenerar oro y comprobar la decisión aplicada**

```bash
python -m oro.construir_cliente_features
```
Expected: sin errores.

```bash
python -c "
import json
import config
from src.db_io import leer_tabla_sqlite
from src.decisiones import decidir_perfil_incompleto
with open(config.OUTPUTS_DIR / 'eda' / 'faltantes_solapamiento.json', encoding='utf-8') as f:
    lift = json.load(f)['lift_estimador_vivienda']
esperado = decidir_perfil_incompleto(lift)['crear_bandera_unica']
df = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
assert ('perfil_incompleto' in df.columns) == esperado, (
    f'lift={lift:.3f} esperaba crear={esperado}')
print(f'OK §5/§6.5.2 (D7) — lift={lift:.3f} -> perfil_incompleto {\"creada\" if esperado else \"NO creada\"}')
"
```
Expected: `OK §5/§6.5.2 (D7) — lift=X.XXX -> perfil_incompleto <creada|NO creada>`

- [ ] **Step 6: Commit**

```bash
git add oro/construir_cliente_features.py tests/test_construir_cliente_features.py
git commit -m "✨feat: add conditional perfil_incompleto flag driven by measured overlap (SPEC_V2 5)"
```

---

## Task 15 [NUEVO]: `src/feature_tests.py` — batería estadística (SPEC_V2 §4)

**Files:**
- Create: `tests/test_feature_tests.py`
- Create: `src/feature_tests.py`

**Interfaces:**
- Produces:
  - `binear(x, n_bins=10, etiqueta_nulos="Sin dato") -> pd.Series`
  - `calcular_woe_iv(x, y, n_bins=10) -> tuple[float, pd.DataFrame]` — el DataFrame tiene `bin, n, eventos, no_eventos, pct_eventos, pct_no_eventos, woe, iv_bin`
  - `clasificar_iv(iv: float) -> str` ∈ `{"descartar","debil","media","fuerte"}`
  - `mann_whitney(x, y) -> dict` con `u, p_valor, mediana_evento, mediana_no_evento`
  - `chi2_y_cramer(x, y) -> dict` con `chi2, p_valor, gl, v_cramer`
  - `benjamini_hochberg(p_valores, alpha=0.05) -> tuple[np.ndarray, np.ndarray]` (q-valores, máscara de rechazo)
  - `calcular_vif(df_numerico) -> pd.DataFrame` con `variable, vif`
  - Consumidas por `notebooks/04_validacion_variables.ipynb` (Task 16) y `notebooks/07_auditoria_sesgo.ipynb` (Task 22).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_feature_tests.py
import numpy as np
import pandas as pd
import pytest

from src.feature_tests import (
    benjamini_hochberg,
    binear,
    calcular_vif,
    calcular_woe_iv,
    chi2_y_cramer,
    clasificar_iv,
    mann_whitney,
)

RNG = np.random.default_rng(42)


# --- IV / WoE ---

def test_iv_alto_cuando_la_variable_separa_la_etiqueta():
    y = pd.Series([0] * 500 + [1] * 500)
    x = pd.Series(list(RNG.normal(0, 1, 500)) + list(RNG.normal(6, 1, 500)))
    iv, tabla = calcular_woe_iv(x, y)
    assert iv > 0.3
    assert clasificar_iv(iv) == "fuerte"
    assert set(tabla.columns) >= {"bin", "n", "eventos", "no_eventos", "woe", "iv_bin"}
    assert tabla["n"].sum() == 1000


def test_iv_bajo_cuando_no_hay_relacion():
    y = pd.Series(RNG.integers(0, 2, 4000))
    x = pd.Series(RNG.normal(0, 1, 4000))
    iv, _ = calcular_woe_iv(x, y)
    assert iv < 0.1


def test_iv_trata_los_nulos_como_un_bin_mas():
    """SPEC_V2 §4: para desc_tipo_de_vivienda, "Sin dato" es un bin más."""
    x = pd.Series(["PROPIA"] * 100 + ["ARRENDADA"] * 100 + [None] * 200)
    y = pd.Series([1] * 50 + [0] * 50 + [1] * 20 + [0] * 80 + [0] * 200)
    iv, tabla = calcular_woe_iv(x, y)
    assert "Sin dato" in tabla["bin"].astype(str).tolist()
    assert tabla["n"].sum() == 400


@pytest.mark.parametrize("iv,esperado", [
    (0.001, "descartar"), (0.019, "descartar"), (0.02, "debil"),
    (0.09, "debil"), (0.1, "media"), (0.29, "media"), (0.3, "fuerte"), (1.2, "fuerte"),
])
def test_clasificar_iv_usa_los_cortes_del_spec(iv, esperado):
    assert clasificar_iv(iv) == esperado


def test_binear_no_falla_con_muchos_empates():
    """Los saldos tienen enormes masas en 0: qcut duplicaría bordes."""
    x = pd.Series([0.0] * 900 + list(range(100)))
    b = binear(x, n_bins=10)
    assert b.notna().all()
    assert b.nunique() >= 2


# --- Mann-Whitney ---

def test_mann_whitney_detecta_diferencia_de_distribucion():
    y = pd.Series([0] * 300 + [1] * 300)
    x = pd.Series(list(RNG.normal(0, 1, 300)) + list(RNG.normal(3, 1, 300)))
    r = mann_whitney(x, y)
    assert r["p_valor"] < 0.001
    assert r["mediana_evento"] > r["mediana_no_evento"]


def test_mann_whitney_ignora_nulos():
    y = pd.Series([0, 0, 1, 1])
    x = pd.Series([1.0, np.nan, 5.0, 6.0])
    r = mann_whitney(x, y)
    assert not np.isnan(r["p_valor"])


def test_mann_whitney_sin_un_grupo_devuelve_nan():
    r = mann_whitney(pd.Series([1.0, 2.0]), pd.Series([0, 0]))
    assert np.isnan(r["p_valor"])


# --- Chi-cuadrado y V de Cramér ---

def test_cramer_cercano_a_uno_con_asociacion_perfecta():
    x = pd.Series(["a"] * 200 + ["b"] * 200)
    y = pd.Series([1] * 200 + [0] * 200)
    r = chi2_y_cramer(x, y)
    assert r["v_cramer"] > 0.95
    assert r["p_valor"] < 1e-10


def test_cramer_cercano_a_cero_con_independencia():
    x = pd.Series(RNG.choice(["a", "b", "c"], 5000))
    y = pd.Series(RNG.integers(0, 2, 5000))
    assert chi2_y_cramer(x, y)["v_cramer"] < 0.1


def test_cramer_trata_nulos_como_categoria():
    x = pd.Series(["a", None, "b", None])
    y = pd.Series([1, 0, 1, 0])
    r = chi2_y_cramer(x, y)
    assert not np.isnan(r["chi2"])


# --- Benjamini-Hochberg ---

def test_benjamini_hochberg_ejemplo_clasico():
    q, rechaza = benjamini_hochberg([0.001, 0.008, 0.039, 0.041, 0.042], alpha=0.05)
    assert rechaza.tolist() == [True, True, True, True, True]
    assert q[0] == pytest.approx(0.005)


def test_benjamini_hochberg_es_mas_estricto_que_alpha_crudo():
    p = [0.001] + [0.04] * 20
    q, rechaza = benjamini_hochberg(p, alpha=0.05)
    assert rechaza[0]
    assert not rechaza[1:].any()   # 0.04 < 0.05 pero no sobrevive la corrección FDR


def test_benjamini_hochberg_q_no_decrece_con_p():
    p = np.array([0.01, 0.02, 0.03, 0.5])
    q, _ = benjamini_hochberg(p)
    assert np.all(np.diff(q) >= -1e-12)


def test_benjamini_hochberg_rechaza_nan():
    with pytest.raises(ValueError):
        benjamini_hochberg([0.01, np.nan])


# --- VIF ---

def test_vif_dispara_con_dependencia_contable():
    """SPEC_V2 §4.5: patrimonio = activos − pasivos por definición contable."""
    activos = RNG.normal(10_000, 2_000, 500)
    pasivos = RNG.normal(3_000, 800, 500)
    df = pd.DataFrame({
        "total_activos": activos,
        "total_pasivos": pasivos,
        "total_patrimonio": activos - pasivos,
    })
    r = calcular_vif(df).set_index("variable")
    assert r.loc["total_patrimonio", "vif"] > 10


def test_vif_cercano_a_uno_con_variables_independientes():
    df = pd.DataFrame({
        "a": RNG.normal(0, 1, 1000),
        "b": RNG.normal(0, 1, 1000),
        "c": RNG.normal(0, 1, 1000),
    })
    r = calcular_vif(df)
    assert (r["vif"] < 1.5).all()
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_feature_tests.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.feature_tests'`

- [ ] **Step 3: Implementar `src/feature_tests.py`**

```python
# src/feature_tests.py
"""Batería de validación estadística de variables (SPEC_V2 §4).

Objetivo: poder justificar la inclusión o exclusión de cada variable con un
criterio explícito, no por intuición.
"""
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu
from sklearn.linear_model import LinearRegression

ETIQUETA_NULOS = "Sin dato"
# Corrección de Haldane-Anscombe: evita log(0) en bins sin eventos o sin no-eventos.
EPS = 0.5


def binear(x, n_bins: int = 10, etiqueta_nulos: str = ETIQUETA_NULOS) -> pd.Series:
    """Bins por cuantiles para continuas, categorías tal cual para el resto.

    Los nulos se convierten SIEMPRE en un bin propio con etiqueta `etiqueta_nulos`
    (SPEC_V2 §4: "calcular el IV tratando 'Sin dato' como un bin más").
    `duplicates="drop"` es indispensable: los saldos tienen masas enormes en 0 y
    varios bordes de cuantil coinciden.
    """
    s = pd.Series(x)
    es_numerica = s.dtype.kind in "biufc"
    if es_numerica and s.nunique(dropna=True) > n_bins:
        binned = pd.qcut(s, q=n_bins, duplicates="drop")
        out = binned.astype(object)
    else:
        out = s.astype(object)
    return out.where(out.notna(), etiqueta_nulos)


def calcular_woe_iv(x, y, n_bins: int = 10,
                    etiqueta_nulos: str = ETIQUETA_NULOS):
    """Information Value y WoE por bin.

    Convención: WoE = ln(%no_eventos / %eventos). El signo depende de la
    convención elegida; el IV es invariante a ella.
    """
    bins = binear(x, n_bins=n_bins, etiqueta_nulos=etiqueta_nulos)
    y = pd.Series(y).astype(int).reset_index(drop=True)
    tab = pd.DataFrame({"bin": bins.reset_index(drop=True).astype(str), "y": y})

    g = tab.groupby("bin", as_index=False)["y"].agg(n="count", eventos="sum")
    g["no_eventos"] = g["n"] - g["eventos"]

    tot_e = g["eventos"].sum()
    tot_ne = g["no_eventos"].sum()
    k = len(g)
    g["pct_eventos"] = (g["eventos"] + EPS) / (tot_e + EPS * k)
    g["pct_no_eventos"] = (g["no_eventos"] + EPS) / (tot_ne + EPS * k)
    g["woe"] = np.log(g["pct_no_eventos"] / g["pct_eventos"])
    g["iv_bin"] = (g["pct_no_eventos"] - g["pct_eventos"]) * g["woe"]

    return float(g["iv_bin"].sum()), g


def clasificar_iv(iv: float) -> str:
    """Cortes estándar de scorecard bancario (SPEC_V2 §4.1)."""
    if iv < 0.02:
        return "descartar"
    if iv < 0.10:
        return "debil"
    if iv < 0.30:
        return "media"
    return "fuerte"


def mann_whitney(x, y) -> dict:
    """Mann-Whitney U para continuas vs. etiqueta (SPEC_V2 §4.2).

    No t-test: los datos financieros son fuertemente asimétricos y el t-test
    asume normalidad de las medias muestrales por grupo.
    """
    s = pd.Series(x).reset_index(drop=True)
    yy = pd.Series(y).astype(int).reset_index(drop=True)
    g1 = s[yy == 1].dropna()
    g0 = s[yy == 0].dropna()
    if len(g1) == 0 or len(g0) == 0:
        return {"u": float("nan"), "p_valor": float("nan"),
                "mediana_evento": float("nan"), "mediana_no_evento": float("nan"),
                "n_evento": int(len(g1)), "n_no_evento": int(len(g0))}
    u, p = mannwhitneyu(g1, g0, alternative="two-sided")
    return {"u": float(u), "p_valor": float(p),
            "mediana_evento": float(g1.median()),
            "mediana_no_evento": float(g0.median()),
            "n_evento": int(len(g1)), "n_no_evento": int(len(g0))}


def chi2_y_cramer(x, y, etiqueta_nulos: str = ETIQUETA_NULOS) -> dict:
    """Chi-cuadrado de independencia + V de Cramér (SPEC_V2 §4.3)."""
    xs = pd.Series(x).astype(object)
    xs = xs.where(xs.notna(), etiqueta_nulos)
    tabla = pd.crosstab(xs.reset_index(drop=True), pd.Series(y).reset_index(drop=True))
    if tabla.shape[0] < 2 or tabla.shape[1] < 2:
        return {"chi2": float("nan"), "p_valor": float("nan"),
                "gl": 0, "v_cramer": float("nan")}
    chi2, p, gl, _ = chi2_contingency(tabla)
    n = tabla.to_numpy().sum()
    k = min(tabla.shape) - 1
    v = float(np.sqrt(chi2 / (n * k))) if k > 0 else float("nan")
    return {"chi2": float(chi2), "p_valor": float(p), "gl": int(gl), "v_cramer": v}


def benjamini_hochberg(p_valores, alpha: float = 0.05):
    """Corrección FDR de Benjamini-Hochberg (SPEC_V2 §4.4).

    Devuelve (q_valores, rechaza). Se prueban decenas de variables a la vez: sin
    corregir, con 40 pruebas a alpha=0.05 se esperan ~2 "significativas" por azar.
    """
    p = np.asarray(p_valores, dtype=float)
    if np.isnan(p).any():
        raise ValueError("benjamini_hochberg no admite p-valores NaN; fíltralos antes")
    n = len(p)
    if n == 0:
        return np.array([]), np.array([], dtype=bool)

    orden = np.argsort(p)
    p_ord = p[orden]
    q_ord = p_ord * n / np.arange(1, n + 1)
    q_ord = np.minimum.accumulate(q_ord[::-1])[::-1]   # monotonía sobre p
    q_ord = np.minimum(q_ord, 1.0)

    q = np.empty(n, dtype=float)
    q[orden] = q_ord
    return q, q <= alpha


def calcular_vif(df_numerico: pd.DataFrame) -> pd.DataFrame:
    """VIF por variable (SPEC_V2 §4.5). Umbral de alerta: VIF > 10.

    VIF_j = 1 / (1 − R²_j), con R²_j la regresión de la variable j sobre el resto.
    """
    X = df_numerico.replace([np.inf, -np.inf], np.nan).dropna()
    filas = []
    for col in X.columns:
        otras = X.drop(columns=[col])
        if otras.shape[1] == 0 or X.shape[0] <= otras.shape[1]:
            filas.append({"variable": col, "vif": float("nan")})
            continue
        r2 = LinearRegression().fit(otras, X[col]).score(otras, X[col])
        vif = float("inf") if r2 >= 1 - 1e-12 else 1.0 / (1.0 - r2)
        filas.append({"variable": col, "vif": float(vif)})
    return pd.DataFrame(filas)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_feature_tests.py -v
```
Expected: `24 passed` (17 funciones, una de ellas parametrizada en 8 casos)

- [ ] **Step 5: Commit**

```bash
git add src/feature_tests.py tests/test_feature_tests.py
git commit -m "✨feat: add IV/WoE, Mann-Whitney, Cramer V, BH-FDR and VIF battery (SPEC_V2 4)"
```

---

## Task 16 [NUEVO]: `notebooks/04_validacion_variables.ipynb` (SPEC_V2 §4, §6.5)

Notebook — verificación de salida.

**Files:**
- Create: `notebooks/04_validacion_variables.ipynb`

**Interfaces:**
- Consumes: `cliente_features`, `src.feature_tests.*`, `src.decisiones.decidir_tratamiento_vivienda`, `src.log_decisiones.registrar_decision`, `src.features_modelo.features_modelo_a`.
- Produces:
  - `outputs/eda/validacion_variables.csv` — **tabla única por variable** con `variable, tipo, iv, clase_iv, p_mann_whitney, p_chi2, v_cramer, q_bh, significativa_fdr, vif, alerta_vif, decision_inclusion`
  - `outputs/eda/woe_por_bin.csv` — WoE por bin de las variables conservadas
  - `outputs/eda/decision_vivienda.json`
  - Filas en el log de decisiones con claves `inclusion_vivienda` y `variables_descartadas_por_iv`.
  - `outputs/eda/validacion_variables.csv` es consumida por `scripts/export_powerbi.py` (Task 25) para armar `fact_importancia_variables.csv`.

- [ ] **Step 1: Celda 0 — carga y clasificación de variables**

```python
import json
import sys
sys.path.insert(0, "..")

import numpy as np
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite
from src.features_modelo import features_modelo_a
from src.feature_tests import (
    benjamini_hochberg, calcular_vif, calcular_woe_iv, chi2_y_cramer,
    clasificar_iv, mann_whitney,
)
from src.log_decisiones import registrar_decision

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
y = df["etiqueta_adopcion"]

# Candidatas = predictoras del Modelo A + las tres demográficas de §6.4.
# desc_genero NO es candidata a entrar al modelo, pero SÍ se mide (§4 y §6.4).
candidatas = sorted(set(features_modelo_a(df.columns)) | {"desc_genero"})

continuas = [c for c in candidatas if df[c].dtype.kind in "biufc"]
categoricas = [c for c in candidatas if c not in continuas]

print(f"{len(candidatas)} variables a validar: {len(continuas)} continuas, "
      f"{len(categoricas)} categóricas")
print(f"Demográficas incluidas en la medición: "
      f"{[c for c in ['desc_genero','grupo_edad','desc_tipo_de_vivienda'] if c in candidatas]}")
```

- [ ] **Step 2: Celda 1 — IV/WoE, Mann-Whitney, chi²/Cramér por variable**

```python
filas = []
woe_frames = []

for col in candidatas:
    es_continua = col in continuas
    iv, tabla_woe = calcular_woe_iv(df[col], y)
    tabla_woe.insert(0, "variable", col)
    woe_frames.append(tabla_woe)

    fila = {
        "variable": col,
        "tipo": "continua" if es_continua else "categorica",
        "n_nulos": int(df[col].isnull().sum()),
        "iv": iv,
        "clase_iv": clasificar_iv(iv),
        "p_mann_whitney": np.nan,
        "chi2": np.nan,
        "p_chi2": np.nan,
        "v_cramer": np.nan,
    }
    if es_continua:
        mw = mann_whitney(df[col], y)
        fila["p_mann_whitney"] = mw["p_valor"]
        fila["mediana_adoptantes"] = mw["mediana_evento"]
        fila["mediana_no_adoptantes"] = mw["mediana_no_evento"]
    else:
        ch = chi2_y_cramer(df[col], y)
        fila.update({"chi2": ch["chi2"], "p_chi2": ch["p_valor"],
                     "v_cramer": ch["v_cramer"]})
    filas.append(fila)

validacion = pd.DataFrame(filas)
woe_por_bin = pd.concat(woe_frames, ignore_index=True)
print(validacion.sort_values("iv", ascending=False).head(20).to_string(index=False))
```

- [ ] **Step 3: Celda 2 — corrección FDR de Benjamini-Hochberg (§4.4)**

```python
# Un p-valor por variable: el de Mann-Whitney si es continua, el de chi² si es
# categórica. Se corrigen TODOS juntos, porque el problema de multiplicidad es
# sobre el conjunto de variables probadas, no por familia de test.
validacion["p_valor"] = validacion["p_mann_whitney"].fillna(validacion["p_chi2"])

con_p = validacion["p_valor"].notna()
q, rechaza = benjamini_hochberg(validacion.loc[con_p, "p_valor"].to_numpy(), alpha=0.05)
validacion.loc[con_p, "q_bh"] = q
validacion.loc[con_p, "significativa_fdr"] = rechaza

n_crudo = int((validacion["p_valor"] < 0.05).sum())
n_fdr = int(validacion["significativa_fdr"].fillna(False).sum())
print(f"Significativas sin corregir: {n_crudo} / {int(con_p.sum())}")
print(f"Significativas tras Benjamini-Hochberg (FDR 5%): {n_fdr}")
```

- [ ] **Step 4: Celda 3 — VIF (§4.5)**

```python
# Atención especial a patrimonio / activos / pasivos, relacionados por
# definición contable (patrimonio = activos − pasivos).
cols_vif = [c for c in continuas if df[c].notna().mean() > 0.5]
muestra = df[cols_vif].sample(n=min(100_000, len(df)), random_state=config.RANDOM_STATE)
vif = calcular_vif(muestra)
vif["alerta_vif"] = vif["vif"] > config.UMBRAL_VIF

validacion = validacion.merge(vif, on="variable", how="left")

print(vif.sort_values("vif", ascending=False).head(15).to_string(index=False))
print(f"\nVariables con VIF > {config.UMBRAL_VIF}: "
      f"{vif.loc[vif['alerta_vif'], 'variable'].tolist()}")
print("Recordatorio SPEC_V2 §4.5: patrimonio, activos y pasivos están ligados "
      "por definición contable; un VIF alto entre ellos es esperado, no un bug.")
```

- [ ] **Step 5: Celda 4 — regla de decisión de vivienda (§6.5)**

```python
from src.decisiones import decidir_tratamiento_vivienda

# IV de la categórica CON "Sin dato" como un bin más (ya viene así de la celda 1)
iv_vivienda = float(validacion.loc[validacion["variable"] == "desc_tipo_de_vivienda", "iv"].iloc[0])
# IV de la bandera binaria por separado (SPEC_V2 §4, último párrafo)
iv_bandera, _ = calcular_woe_iv(df["tiene_dato_vivienda"], y)

decision_viv = decidir_tratamiento_vivienda(iv_vivienda, iv_bandera)

# Verificación previa obligatoria de §6.5: ¿"tiene dato de vivienda" codifica
# vinculación crediticia en vez de patrimonio?
comparacion = []
for col in ["total_patrimonio", "ingresos_mensuales", "n_productos_no_etiqueta"]:
    mw = mann_whitney(df[col], df["tiene_dato_vivienda"])
    comparacion.append({"variable": col,
                        "mediana_con_dato": mw["mediana_evento"],
                        "mediana_sin_dato": mw["mediana_no_evento"],
                        "p_valor": mw["p_valor"]})
comparacion = pd.DataFrame(comparacion)

tasa_por_nivel = (
    df.groupby("desc_tipo_de_vivienda")["etiqueta_adopcion"]
    .agg(n_clientes="count", tasa_adopcion="mean").reset_index()
)

print(f"IV categórica (con 'Sin dato'): {iv_vivienda:.4f}")
print(f"IV bandera tiene_dato_vivienda: {iv_bandera:.4f}")
print(f"DECISIÓN: {decision_viv['accion']}\n")
print("Sesgo de captura — comparación con/sin dato (§6.5, verificación previa):")
print(comparacion.to_string(index=False))
print("\nTasa de adopción por nivel (incluido 'Sin dato'):")
print(tasa_por_nivel.to_string(index=False))

with open(config.OUTPUTS_DIR / "eda" / "decision_vivienda.json", "w", encoding="utf-8") as f:
    json.dump({**decision_viv,
               "comparacion_sesgo_captura": comparacion.to_dict(orient="records"),
               "tasa_por_nivel": tasa_por_nivel.to_dict(orient="records")},
              f, indent=2, ensure_ascii=False, default=str)

registrar_decision(
    clave="inclusion_vivienda",
    decision=decision_viv["accion"],
    motivo=f"IV categórica={iv_vivienda:.4f}, IV bandera={iv_bandera:.4f}, "
           f"umbral={config.UMBRAL_IV_MINIMO} (SPEC_V2 §6.5)",
    evidencia=decision_viv,
)
```

- [ ] **Step 6: Celda 5 — tabla única de decisión por variable**

```python
def decidir_inclusion(fila):
    # SPEC_V2 §6.4: género se mide pero NUNCA entra, por criterio de idoneidad
    if fila["variable"] == "desc_genero":
        return "excluida_por_idoneidad_no_por_poder_predictivo"
    if fila["variable"] == "desc_tipo_de_vivienda":
        return ("incluir" if decision_viv["conservar_categorica"]
                else "excluir_categorica_" + ("usar_bandera" if decision_viv["conservar_bandera"]
                                              else "descartar_bloque"))
    if fila["variable"] == "tiene_dato_vivienda":
        return "incluir" if decision_viv["conservar_bandera"] or decision_viv["conservar_categorica"] else "descartar"
    if fila["clase_iv"] == "descartar":
        return "descartar_iv_insuficiente"
    # OJO: para las categóricas `alerta_vif` es NaN (el VIF solo se calcula sobre
    # continuas), y `bool(nan)` es True. Hay que comparar explícitamente.
    if fila.get("alerta_vif") is True or fila.get("alerta_vif") == True:  # noqa: E712
        return "incluir_con_alerta_multicolinealidad"
    return "incluir"

validacion["decision_inclusion"] = validacion.apply(decidir_inclusion, axis=1)

orden = ["variable", "tipo", "n_nulos", "iv", "clase_iv", "p_mann_whitney",
         "chi2", "p_chi2", "v_cramer", "p_valor", "q_bh", "significativa_fdr",
         "vif", "alerta_vif", "decision_inclusion"]
validacion = validacion[[c for c in orden if c in validacion.columns]]
validacion = validacion.sort_values("iv", ascending=False)
validacion.to_csv(config.OUTPUTS_DIR / "eda" / "validacion_variables.csv", index=False)

# WoE por bin solo de las variables que se conservan (SPEC_V2 §4.1)
conservadas = set(validacion.loc[
    validacion["decision_inclusion"].str.startswith("incluir"), "variable"])
woe_por_bin[woe_por_bin["variable"].isin(conservadas)].to_csv(
    config.OUTPUTS_DIR / "eda" / "woe_por_bin.csv", index=False)

descartadas = validacion.loc[
    validacion["decision_inclusion"] == "descartar_iv_insuficiente", "variable"].tolist()
registrar_decision(
    clave="variables_descartadas_por_iv",
    decision=f"{len(descartadas)} variables descartadas",
    motivo=f"IV < {config.UMBRAL_IV_MINIMO} (SPEC_V2 §4.1)",
    evidencia={"variables": descartadas},
)

print(validacion.to_string(index=False))
print(f"\nConservadas: {len(conservadas)} | Descartadas por IV: {len(descartadas)}")
print("\nSPEC_V2 §6.4 — desc_genero se midió y se reporta, pero su exclusión está "
      "decidida por criterio de idoneidad financiera, NO por su poder predictivo.")
```

- [ ] **Step 7: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/04_validacion_variables.ipynb
```
Expected: exit code 0.

- [ ] **Step 8: Verificar las salidas**

```bash
python -c "
import json
import pandas as pd
import config
from src.decisiones import decidir_tratamiento_vivienda

v = pd.read_csv(config.OUTPUTS_DIR / 'eda' / 'validacion_variables.csv')
requeridas = {'variable','tipo','iv','clase_iv','q_bh','significativa_fdr','vif','decision_inclusion'}
assert requeridas <= set(v.columns), requeridas - set(v.columns)

# las tres demográficas de §6.4 tienen que estar medidas
for c in ['desc_genero','grupo_edad','desc_tipo_de_vivienda']:
    assert c in set(v['variable']), f'{c} no se midió'

# género: medido pero nunca incluido
g = v.loc[v['variable']=='desc_genero','decision_inclusion'].iloc[0]
assert g.startswith('excluida_por_idoneidad'), g

assert v['iv'].notna().all()
assert (v['iv'] >= 0).all()

with open(config.OUTPUTS_DIR / 'eda' / 'decision_vivienda.json', encoding='utf-8') as f:
    dv = json.load(f)
esperada = decidir_tratamiento_vivienda(dv['iv_categorica'], dv['iv_bandera'])['accion']
assert dv['accion'] == esperada, 'la decision de vivienda no sigue la tabla de 6.5'

w = pd.read_csv(config.OUTPUTS_DIR / 'eda' / 'woe_por_bin.csv')
assert len(w) > 0

print(f'OK §4 — {len(v)} variables validadas | vivienda: {dv[\"accion\"]}')
print(v[['variable','iv','clase_iv','decision_inclusion']].head(15).to_string(index=False))
"
```
Expected: `OK §4 — <N> variables validadas | vivienda: <acción>` + la cabecera de la tabla.

- [ ] **Step 9: Commit**

```bash
git add notebooks/04_validacion_variables.ipynb
git commit -m "✨feat: add statistical variable validation notebook (SPEC_V2 4, 6.5)"
```

---

# FASE 5 — Modelos (SPEC_V2 §6)

---

## Task 17 [NUEVO]: `src/niveles.py` — niveles de prioridad por población (SPEC_V2 §6.2)

**Files:**
- Create: `tests/test_niveles.py`
- Create: `src/niveles.py`

**Interfaces:**
- Produces: `asignar_niveles(valores, etiquetas=("D","C","B","A")) -> pd.Series` (cuartiles; `"A"` = cuartil superior) y `asignar_niveles_por_poblacion(df, col_valor, col_poblacion) -> pd.Series`. Consumidas por `notebooks/02_modelado.ipynb` (Task 18) y `notebooks/05_dimensionamiento.ipynb` (Task 23).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_niveles.py
import numpy as np
import pandas as pd

from src.niveles import asignar_niveles, asignar_niveles_por_poblacion


def test_cuartiles_reparten_en_cuatro_bloques_iguales():
    niveles = asignar_niveles(pd.Series(range(100)))
    assert niveles.value_counts().to_dict() == {"A": 25, "B": 25, "C": 25, "D": 25}
    assert niveles.iloc[99] == "A"     # el valor más alto va al nivel A
    assert niveles.iloc[0] == "D"


def test_muchos_empates_no_rompen_el_corte():
    """Los scores de propensión tienen masas grandes en valores bajos:
    qcut fallaría por bordes duplicados."""
    valores = pd.Series([0.0] * 80 + [0.5] * 10 + [0.9] * 10)
    niveles = asignar_niveles(valores)
    assert niveles.notna().all()
    assert set(niveles) == {"A", "B", "C", "D"}
    assert niveles.iloc[-1] == "A"


def test_nulos_quedan_sin_nivel():
    valores = pd.Series([1.0, 2.0, np.nan, 4.0])
    niveles = asignar_niveles(valores)
    assert pd.isna(niveles.iloc[2])
    assert niveles.iloc[3] == "A"


def test_serie_vacia_o_toda_nula_devuelve_todo_nulo():
    assert asignar_niveles(pd.Series([np.nan, np.nan])).isna().all()
    assert len(asignar_niveles(pd.Series([], dtype=float))) == 0


def test_por_poblacion_los_cuartiles_son_independientes():
    """SPEC_V2 §6.2: A/B/C/D se asignan por separado DENTRO de cada población,
    para no comparar poblaciones no comparables."""
    df = pd.DataFrame({
        "valor": [1, 2, 3, 4, 100, 200, 300, 400],
        "poblacion": ["sin_historial"] * 4 + ["con_historial"] * 4,
    })
    niveles = asignar_niveles_por_poblacion(df, "valor", "poblacion")
    # el 4 es el mejor de su población -> A, aunque sea 100x menor que el peor de la otra
    assert niveles.iloc[3] == "A"
    assert niveles.iloc[4] == "D"      # el 100 es el peor de la suya
    assert niveles.iloc[7] == "A"


def test_por_poblacion_conserva_el_indice_original():
    df = pd.DataFrame({"valor": [3.0, 1.0, 2.0], "poblacion": ["x", "x", "x"]},
                      index=[10, 20, 30])
    niveles = asignar_niveles_por_poblacion(df, "valor", "poblacion")
    assert niveles.index.tolist() == [10, 20, 30]
    assert niveles.loc[10] == "A"
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_niveles.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.niveles'`

- [ ] **Step 3: Implementar `src/niveles.py`**

```python
# src/niveles.py
"""Asignación de niveles de prioridad A/B/C/D por cuartiles (SPEC_V2 §6.2).

Criterio de corte documentado: cuartiles del RANGO PERCENTIL, no de los valores.
Con `pd.qcut` sobre los valores directamente, las masas de empates (muchísimos
scores idénticos y muchos valores esperados en 0) producen bordes duplicados y
el corte falla o queda desbalanceado. El rango percentil con `method="first"`
rompe empates por orden de aparición y garantiza cuatro bloques del 25%.

A = cuartil superior (mayor prioridad), D = cuartil inferior.
"""
import pandas as pd

ETIQUETAS_POR_DEFECTO = ("D", "C", "B", "A")


def asignar_niveles(valores, etiquetas=ETIQUETAS_POR_DEFECTO) -> pd.Series:
    s = pd.Series(valores)
    resultado = pd.Series(pd.NA, index=s.index, dtype=object)
    validos = s.notna()
    if not validos.any():
        return resultado

    rangos = s[validos].rank(method="first", pct=True)
    cortados = pd.cut(
        rangos, bins=[0.0, 0.25, 0.5, 0.75, 1.0],
        labels=list(etiquetas), include_lowest=True,
    )
    resultado.loc[validos] = cortados.astype(object)
    return resultado


def asignar_niveles_por_poblacion(df: pd.DataFrame, col_valor: str,
                                  col_poblacion: str,
                                  etiquetas=ETIQUETAS_POR_DEFECTO) -> pd.Series:
    """Cuartiles calculados DENTRO de cada población por separado."""
    resultado = pd.Series(pd.NA, index=df.index, dtype=object)
    for _, grupo in df.groupby(col_poblacion, dropna=False):
        resultado.loc[grupo.index] = asignar_niveles(grupo[col_valor], etiquetas)
    return resultado
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_niveles.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/niveles.py tests/test_niveles.py
git commit -m "✨feat: add quartile priority levels computed within each population (SPEC_V2 6.2)"
```

---

## Task 18 [MODIFICA]: `02_modelado.ipynb` — Modelos A y B + niveles (SPEC_V2 §6.1, §6.2)

Reescribe el notebook corregido en la Task 5 para producir las dos variantes.

**Files:**
- Modify: `notebooks/02_modelado.ipynb`

**Interfaces:**
- Consumes: `cliente_features`, `src.features_modelo.features_modelo_a/b`, `src.niveles.asignar_niveles_por_poblacion`, `src.fuga.validar_sin_fuga`.
- Produces:
  - tabla `fact_cliente_score` en `oro.db` — `numero_id, score, modelo_usado, tiene_historial_producto, poblacion, valor_referencia, nivel` (columnas de monto se añaden en la Task 20)
  - `outputs/models/propension_modelo_a.pkl`, `propension_modelo_b.pkl`
  - `outputs/models/metricas_propension.json` — `{modelo_a: {...}, modelo_b: {...}, modelo_a_solo_con_productos: {...}}`
  - `outputs/models/importancia_permutacion.csv` — `variable, importancia, modelo`

- [ ] **Step 1: Reemplazar la celda 0 (dataset y split)**

```python
import json
import sys
sys.path.insert(0, "..")

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

import config
from src.db_io import escribir_tabla_sqlite, leer_tabla_sqlite
from src.features_modelo import features_modelo_a, features_modelo_b
from src.fuga import validar_sin_fuga
from src.niveles import asignar_niveles_por_poblacion

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
(config.OUTPUTS_DIR / "models").mkdir(parents=True, exist_ok=True)

CATEGORICAS = ["desc_segmento", "grupo_edad", "desc_tipo_de_vivienda"]


def preparar_matriz(datos, feature_cols, contexto):
    validar_sin_fuga(feature_cols, contexto=contexto)
    X = pd.get_dummies(
        datos[feature_cols],
        columns=[c for c in CATEGORICAS if c in feature_cols],
        dummy_na=False,
    )
    validar_sin_fuga(X.columns, contexto=f"{contexto} (post get_dummies)")
    return X


# SPEC_V2 §6.1: AMBOS modelos se entrenan sobre toda la base apta.
entrenables = df[df["apto_entrenamiento"] == 1].reset_index(drop=True)
y = entrenables["etiqueta_adopcion"]

cols_a = features_modelo_a(entrenables.columns)
cols_b = features_modelo_b(entrenables.columns)
Xa = preparar_matriz(entrenables, cols_a, "Modelo A")
Xb = preparar_matriz(entrenables, cols_b, "Modelo B")

idx_train, idx_test = train_test_split(
    np.arange(len(entrenables)), test_size=config.TEST_SIZE,
    random_state=config.RANDOM_STATE, stratify=y,
)
print(f"entrenables: {len(entrenables):,} de {len(df):,}")
print(f"Modelo A: {Xa.shape[1]} features | Modelo B: {Xb.shape[1]} features")
print(f"tasa de adopción: {y.mean():.4f}")
```

- [ ] **Step 2: Celda 1 — entrenar y evaluar ambos modelos**

```python
def entrenar_y_evaluar(X, nombre):
    X_tr, X_te = X.iloc[idx_train], X.iloc[idx_test]
    y_tr, y_te = y.iloc[idx_train], y.iloc[idx_test]
    modelo = HistGradientBoostingClassifier(random_state=config.RANDOM_STATE)
    modelo.fit(X_tr, y_tr)
    proba_te = modelo.predict_proba(X_te)[:, 1]
    auc = float(roc_auc_score(y_te, proba_te))
    print(f"{nombre}: AUC = {auc:.4f}  (n_train={len(X_tr):,}, n_test={len(X_te):,})")
    assert auc <= config.UMBRAL_AUC_FUGA, (
        f"{nombre}: AUC={auc:.4f} > {config.UMBRAL_AUC_FUGA}. "
        "SPEC_V2 §1: asumir fuga residual e investigar antes de continuar."
    )
    return modelo, auc, proba_te


modelo_a, auc_a, proba_a_te = entrenar_y_evaluar(Xa, "Modelo A (completo)")
modelo_b, auc_b, proba_b_te = entrenar_y_evaluar(Xb, "Modelo B (cold-start)")

# SPEC_V2 §6.1: también el AUC de A restringido al subconjunto CON productos.
tiene_prod_te = entrenables.iloc[idx_test]["tiene_historial_producto"].to_numpy() == 1
y_te = y.iloc[idx_test].to_numpy()
auc_a_con_productos = float(roc_auc_score(y_te[tiene_prod_te], proba_a_te[tiene_prod_te]))
print(f"Modelo A restringido a clientes CON productos: AUC = {auc_a_con_productos:.4f} "
      f"(n={int(tiene_prod_te.sum()):,})")

metricas = {
    "modelo_a": {"auc": auc_a, "n_features": int(Xa.shape[1])},
    "modelo_b": {"auc": auc_b, "n_features": int(Xb.shape[1])},
    "modelo_a_solo_con_productos": {"auc": auc_a_con_productos,
                                    "n": int(tiene_prod_te.sum())},
    "n_entrenables": int(len(entrenables)),
    "tasa_adopcion": float(y.mean()),
}
with open(config.OUTPUTS_DIR / "models" / "metricas_propension.json", "w") as f:
    json.dump(metricas, f, indent=2)
joblib.dump(modelo_a, config.OUTPUTS_DIR / "models" / "propension_modelo_a.pkl")
joblib.dump(modelo_b, config.OUTPUTS_DIR / "models" / "propension_modelo_b.pkl")
```

- [ ] **Step 3: Celda 2 — permutation importance (§4.6)**

```python
# SPEC_V2 §4.6: permutation importance post-entrenamiento, más confiable que la
# importancia nativa de árboles (que sobrevalora las variables de alta cardinalidad).
frames = []
for modelo, X, nombre in [(modelo_a, Xa, "A"), (modelo_b, Xb, "B")]:
    X_te = X.iloc[idx_test]
    sub = X_te.sample(n=min(30_000, len(X_te)), random_state=config.RANDOM_STATE)
    pi = permutation_importance(
        modelo, sub, y.iloc[idx_test].loc[sub.index], n_repeats=5,
        random_state=config.RANDOM_STATE, scoring="roc_auc",
    )
    frames.append(pd.DataFrame({
        "variable": sub.columns,
        "importancia": pi.importances_mean,
        "importancia_std": pi.importances_std,
        "modelo": nombre,
    }))

importancia = pd.concat(frames, ignore_index=True).sort_values(
    ["modelo", "importancia"], ascending=[True, False])
importancia.to_csv(config.OUTPUTS_DIR / "models" / "importancia_permutacion.csv", index=False)
print(importancia.groupby("modelo").head(10).to_string(index=False))
```

- [ ] **Step 4: Celda 3 — scoring de TODA la base (§2, §6.1)**

```python
# SPEC_V2 §2: ningún cliente queda sin score.
# §6.1: Modelo A se aplica a clientes con al menos un producto; Modelo B a los
# clientes sin ningún producto.
Xa_full = preparar_matriz(df, cols_a, "Modelo A scoring").reindex(
    columns=Xa.columns, fill_value=False)
Xb_full = preparar_matriz(df, cols_b, "Modelo B scoring").reindex(
    columns=Xb.columns, fill_value=False)

con_producto = df["tiene_historial_producto"] == 1

scores = pd.Series(np.nan, index=df.index, dtype=float)
scores[con_producto] = modelo_a.predict_proba(Xa_full[con_producto])[:, 1]
scores[~con_producto] = modelo_b.predict_proba(Xb_full[~con_producto])[:, 1]

fact = pd.DataFrame({
    "numero_id": df["numero_id"],
    "score": scores,
    "modelo_usado": np.where(con_producto, "A", "B"),
    "tiene_historial_producto": df["tiene_historial_producto"],
    "apto_entrenamiento": df["apto_entrenamiento"],
    "poblacion": np.where(con_producto, "con_historial", "sin_historial"),
})
assert fact["score"].notna().all(), "hay clientes sin score: viola SPEC_V2 §2"
print(f"scoreados: {len(fact):,} clientes "
      f"({int(con_producto.sum()):,} con modelo A, {int((~con_producto).sum()):,} con modelo B)")
```

- [ ] **Step 5: Celda 4 — niveles de prioridad por población (§6.2)**

```python
# SPEC_V2 §6.2:
#  - población CON historial de inversión: ordenar por valor_esperado = score × monto_estimado_12m
#  - población SIN historial: ordenar por score, con capacidad_ahorro_anualizada como
#    referencia de valor, etiquetada explícitamente como PROXY, no como pronóstico.
# El monto (Task 20 / notebook 06) aún no existe: en este paso el valor de referencia
# de la población con historial es el score. El notebook 06 recalcula los niveles de
# esa población con el valor esperado y sobrescribe fact_cliente_score.
fact["capacidad_ahorro_anualizada"] = (df["capacidad_ahorro"] * 12).to_numpy()
fact["valor_referencia"] = np.where(
    con_producto, fact["score"], fact["capacidad_ahorro_anualizada"] * fact["score"])
fact["tipo_valor_referencia"] = np.where(
    con_producto, "score_propension",
    "proxy_capacidad_ahorro_anualizada_x_score_similitud")

fact["nivel"] = asignar_niveles_por_poblacion(fact, "valor_referencia", "poblacion")

escribir_tabla_sqlite(fact, config.ORO_DB, "fact_cliente_score")

print(pd.crosstab(fact["poblacion"], fact["nivel"]).to_string())
print(
    "\nSPEC_V2 §6.1 — RESTRICCIÓN DE INTERPRETACIÓN: para el segmento sin productos "
    "la etiqueta es 0 por construcción (no puede haber positivos). El score del "
    "Modelo B sobre ese segmento es un PUNTAJE DE SIMILITUD (lookalike), no una "
    "probabilidad validada. Se reporta como ranking relativo por niveles A/B/C/D, "
    "NUNCA como porcentaje de probabilidad.\n"
    "\nSPEC_V2 §6.2 — CRITERIO DE CORTE: cuartiles del rango percentil calculados "
    "DENTRO de cada población por separado. Un cliente 'A' sin historial y un "
    "cliente 'A' con historial no son comparables entre sí: cada uno es del 25% "
    "superior de SU población."
)
```

- [ ] **Step 6: Celda 5 — curva top-N (conservar, adaptada)**

```python
# Targeting de campaña: qué recall/precisión se obtiene contactando el top N%.
# Se calcula sobre el TEST del Modelo A, la única población con positivos reales.
orden = np.argsort(-proba_a_te)
y_ord = y.iloc[idx_test].to_numpy()[orden]
n = len(y_ord)

filas = []
for pct in [0.01, 0.05, 0.10, 0.20]:
    corte = max(1, int(np.ceil(n * pct)))
    sel = y_ord[:corte]
    filas.append({"top_pct": pct, "n_contactados": corte,
                  "precision": sel.sum() / corte,
                  "recall": sel.sum() / y_ord.sum()})
curva = pd.DataFrame(filas)
curva.to_csv(config.OUTPUTS_DIR / "models" / "curva_precision_recall.csv", index=False)
print(curva.to_string(index=False))
```

- [ ] **Step 7: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_modelado.ipynb
```
Expected: exit code 0. Si un AUC supera 0.95, el `assert` corta la ejecución: investigar fuga residual (SPEC_V2 §1).

- [ ] **Step 8: Verificar**

```bash
python -c "
import json
import config
from src.db_io import leer_tabla_sqlite

with open(config.OUTPUTS_DIR / 'models' / 'metricas_propension.json') as f:
    m = json.load(f)
for k in ['modelo_a','modelo_b','modelo_a_solo_con_productos']:
    assert 0.5 <= m[k]['auc'] <= config.UMBRAL_AUC_FUGA, (k, m[k])

f = leer_tabla_sqlite(config.ORO_DB, 'fact_cliente_score')
cf = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
assert len(f) == len(cf), 'SPEC_V2 §2: toda la base debe tener score'
assert f['score'].notna().all()
assert f['score'].between(0, 1).all()
assert set(f['modelo_usado']) == {'A','B'}
assert set(f['poblacion']) == {'con_historial','sin_historial'}
assert f['nivel'].notna().all()
# los cuartiles se calculan DENTRO de cada población
for pob, g in f.groupby('poblacion'):
    prop = g['nivel'].value_counts(normalize=True)
    assert abs(prop['A'] - 0.25) < 0.01, (pob, prop.to_dict())
print(f'OK §6.1/§6.2 — A={m[\"modelo_a\"][\"auc\"]:.4f} B={m[\"modelo_b\"][\"auc\"]:.4f} '
      f'A|con_productos={m[\"modelo_a_solo_con_productos\"][\"auc\"]:.4f} | {len(f):,} scoreados')
"
```
Expected: `OK §6.1/§6.2 — A=0.xxxx B=0.xxxx A|con_productos=0.xxxx | 860223 scoreados`

- [ ] **Step 9: Commit**

```bash
git add notebooks/02_modelado.ipynb
git commit -m "✨feat: train propensity models A and B, score full base, assign per-population levels (SPEC_V2 6.1, 6.2)"
```

---

## Task 18B [NUEVO]: análisis de sensibilidad de la etiqueta con recencia estricta (D0)

D0 exige reentrenar el Modelo A con la etiqueta alternativa `etiqueta_adopcion_reciente` (Task 2B) y comparar contra el modelo principal de la Task 18: AUC de ambos, correlación de Spearman entre los dos rankings de clientes, y porcentaje de clientes que cambian de nivel de prioridad. **Solo el Modelo A** (N6): en la población del Modelo B la etiqueta es 0 por construcción, así que no hay nada que comparar.

**Files:**
- Modify: `notebooks/02_modelado.ipynb`

**Interfaces:**
- Consumes: `entrenables`, `cols_a`, `Xa`, `Xa_full`, `idx_train`, `idx_test`, `con_producto`, `fact` (variables del kernel dejadas por la Task 18).
- Produces: `outputs/models/sensibilidad_recencia_etiqueta.json` — `{auc_principal, auc_reciente, spearman_rho, spearman_p, pct_clientes_cambian_nivel, n_clientes_comparados}`.

- [ ] **Step 1: Celda 6 — reentrenar Modelo A con la etiqueta alternativa**

```python
from scipy.stats import spearmanr

y_reciente = entrenables["etiqueta_adopcion_reciente"]

modelo_a_reciente = HistGradientBoostingClassifier(random_state=config.RANDOM_STATE)
modelo_a_reciente.fit(Xa.iloc[idx_train], y_reciente.iloc[idx_train])

proba_reciente_te = modelo_a_reciente.predict_proba(Xa.iloc[idx_test])[:, 1]
auc_reciente = float(roc_auc_score(y_reciente.iloc[idx_test], proba_reciente_te))

print(f"Modelo A (etiqueta principal):   AUC = {auc_a:.4f}")
print(f"Modelo A (etiqueta reciente, D0): AUC = {auc_reciente:.4f}")
print(f"Diferencia de AUC: {auc_reciente - auc_a:+.4f}")
```

- [ ] **Step 2: Celda 7 — Spearman y cambio de nivel sobre TODA la población con producto**

```python
# Scores de ambos modelos sobre la misma población (clientes con al menos un
# producto, donde aplica el Modelo A) para comparar rankings completos, no
# solo el test set.
scores_reciente_full = pd.Series(
    modelo_a_reciente.predict_proba(Xa_full[con_producto])[:, 1],
    index=df.index[con_producto],
)
scores_principal_full = fact.loc[con_producto, "score"].reset_index(drop=True)
scores_reciente_full = scores_reciente_full.reset_index(drop=True)

rho, p_valor = spearmanr(scores_principal_full, scores_reciente_full)

niveles_principal = asignar_niveles_por_poblacion(
    pd.DataFrame({"valor": scores_principal_full, "g": "x"}), "valor", "g")
niveles_reciente = asignar_niveles_por_poblacion(
    pd.DataFrame({"valor": scores_reciente_full, "g": "x"}), "valor", "g")
cambia_nivel = (niveles_principal.to_numpy() != niveles_reciente.to_numpy())
pct_cambia = float(cambia_nivel.mean())

sensibilidad = {
    "auc_principal": auc_a,
    "auc_reciente": auc_reciente,
    "spearman_rho": float(rho),
    "spearman_p": float(p_valor),
    "pct_clientes_cambian_nivel": pct_cambia,
    "n_clientes_comparados": int(con_producto.sum()),
}
with open(config.OUTPUTS_DIR / "models" / "sensibilidad_recencia_etiqueta.json", "w") as f:
    json.dump(sensibilidad, f, indent=2)

print(f"Spearman rho = {rho:.4f} (p = {p_valor:.2e})")
print(f"Clientes que cambian de nivel A/B/C/D: {pct_cambia:.2%} "
      f"({int(cambia_nivel.sum()):,} de {int(con_producto.sum()):,})")
print(
    "\nSPEC_V2/D0 — INTERPRETACIÓN: si el ranking se mantiene estable "
    "(rho alto, pocos cambios de nivel), la decisión de NO exigir recencia en "
    "la etiqueta no es determinante para el resultado práctico. Si cambia "
    "sustancialmente, reportar ambos escenarios al negocio en vez de uno solo."
)
```

- [ ] **Step 3: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_modelado.ipynb
```
Expected: exit code 0.

- [ ] **Step 4: Verificar**

```bash
python -c "
import json
import config
with open(config.OUTPUTS_DIR / 'models' / 'sensibilidad_recencia_etiqueta.json') as f:
    s = json.load(f)
assert 0.5 <= s['auc_principal'] <= 1.0
assert 0.5 <= s['auc_reciente'] <= 1.0
assert -1.0 <= s['spearman_rho'] <= 1.0
assert 0.0 <= s['pct_clientes_cambian_nivel'] <= 1.0
assert s['n_clientes_comparados'] > 0
print(f'OK D0 — AUC principal={s[\"auc_principal\"]:.4f} vs reciente={s[\"auc_reciente\"]:.4f} | '
      f'rho={s[\"spearman_rho\"]:.4f} | {s[\"pct_clientes_cambian_nivel\"]:.2%} cambian de nivel')
"
```
Expected: `OK D0 — AUC principal=0.xxxx vs reciente=0.xxxx | rho=0.xxxx | X.XX% cambian de nivel`

- [ ] **Step 5: Commit**

```bash
git add notebooks/02_modelado.ipynb
git commit -m "✨feat: add label-recency sensitivity analysis for propensity model A (D0)"
```

---

## Task 19 [NUEVO]: `src/monto.py` — crecimiento, backtesting y escenarios (SPEC_V2 §6.3)

**Files:**
- Create: `tests/test_monto.py`
- Create: `src/monto.py`

**Interfaces:**
- Consumes: `config.MESES_VALIDACION_BACKTEST`.
- Produces:
  - `crecimiento_anualizado(saldo_inicial, saldo_final, meses) -> pd.Series` (crecimiento absoluto escalado a 12 meses; NaN si `meses <= 0`)
  - `split_backtesting_temporal(panel, col_mes, n_meses_validacion=3) -> tuple[pd.DataFrame, pd.DataFrame]`
  - `mae_mape(y_real, y_pred, eps=1.0) -> dict` con `mae, mape, n, n_mape`
  - `escenarios_desde_errores(predicciones, errores, p_bajo=25, p_alto=75) -> pd.DataFrame` con `conservador, base, optimista`
  - Consumidas por `notebooks/06_monto_12m.ipynb` (Task 20).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_monto.py
import numpy as np
import pandas as pd
import pytest

from src.monto import (
    crecimiento_anualizado,
    escenarios_desde_errores,
    mae_mape,
    split_backtesting_temporal,
)


def test_crecimiento_anualizado_escala_a_doce_meses():
    # +600 en 6 meses -> +1200 anualizado
    r = crecimiento_anualizado(pd.Series([1000.0]), pd.Series([1600.0]), pd.Series([6]))
    assert r.iloc[0] == pytest.approx(1200.0)


def test_crecimiento_anualizado_admite_decrecimiento():
    r = crecimiento_anualizado(pd.Series([1000.0]), pd.Series([700.0]), pd.Series([6]))
    assert r.iloc[0] == pytest.approx(-600.0)


def test_crecimiento_anualizado_con_cero_meses_es_nulo_no_infinito():
    r = crecimiento_anualizado(pd.Series([100.0]), pd.Series([200.0]), pd.Series([0]))
    assert pd.isna(r.iloc[0])
    assert not np.isinf(r.to_numpy(dtype=float, na_value=0.0)).any()


def test_split_temporal_deja_los_ultimos_n_meses_para_validacion():
    """SPEC_V2 §6.3.4: entrenar con los primeros N−3 meses, validar contra los últimos 3."""
    panel = pd.DataFrame({
        "numero_id": [1] * 12,
        "mes": pd.date_range("2025-07-01", periods=12, freq="MS"),
        "saldo_mes": range(12),
    })
    train, valid = split_backtesting_temporal(panel, "mes", n_meses_validacion=3)
    assert train["mes"].max() < valid["mes"].min()
    assert valid["mes"].nunique() == 3
    assert train["mes"].nunique() == 9
    assert len(train) + len(valid) == len(panel)


def test_split_temporal_lanza_si_no_hay_historia_suficiente():
    panel = pd.DataFrame({
        "numero_id": [1, 1],
        "mes": pd.to_datetime(["2026-01-01", "2026-02-01"]),
        "saldo_mes": [1.0, 2.0],
    })
    with pytest.raises(ValueError):
        split_backtesting_temporal(panel, "mes", n_meses_validacion=3)


def test_mae_mape():
    r = mae_mape([100.0, 200.0], [110.0, 180.0])
    assert r["mae"] == pytest.approx(15.0)
    assert r["mape"] == pytest.approx((0.10 + 0.10) / 2)
    assert r["n"] == 2


def test_mape_excluye_denominadores_cercanos_a_cero():
    r = mae_mape([0.0, 100.0], [50.0, 110.0], eps=1.0)
    assert r["n"] == 2
    assert r["n_mape"] == 1          # el real 0.0 no entra al MAPE
    assert r["mape"] == pytest.approx(0.10)


def test_mae_mape_ignora_nan():
    r = mae_mape([100.0, np.nan], [110.0, 5.0])
    assert r["n"] == 1
    assert r["mae"] == pytest.approx(10.0)


def test_escenarios_ordenan_conservador_base_optimista():
    """SPEC_V2 §6.3.5: conservador = p25 del error, base = predicción, optimista = p75."""
    errores = np.array([-50.0, -20.0, 0.0, 20.0, 50.0])   # p25=-20, p75=20
    r = escenarios_desde_errores(pd.Series([1000.0, 2000.0]), errores)
    assert r.loc[0, "base"] == 1000.0
    assert r.loc[0, "conservador"] == pytest.approx(980.0)
    assert r.loc[0, "optimista"] == pytest.approx(1020.0)
    assert (r["conservador"] <= r["base"]).all()
    assert (r["base"] <= r["optimista"]).all()


def test_escenarios_conservan_el_indice():
    r = escenarios_desde_errores(pd.Series([10.0], index=[7]), np.array([-1.0, 1.0]))
    assert r.index.tolist() == [7]
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_monto.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.monto'`

- [ ] **Step 3: Implementar `src/monto.py`**

```python
# src/monto.py
"""Modelo de monto a 12 meses: crecimiento, backtesting y escenarios (SPEC_V2 §6.3).

LIMITACIÓN estructural que el notebook debe documentar: con ~13 meses de historia
no es posible validar un horizonte de 12 meses de forma rigurosa ni capturar
estacionalidad anual. El backtest valida contra 3 meses; los 12 meses son una
extrapolación. El resultado se reporta SIEMPRE como rango, nunca como cifra única.
"""
import numpy as np
import pandas as pd

import config


def crecimiento_anualizado(saldo_inicial, saldo_final, meses) -> pd.Series:
    """Crecimiento ABSOLUTO observado, escalado linealmente a 12 meses.

    Absoluto y no compuesto: con saldos que arrancan en 0 (adquisición en frío)
    una tasa compuesta es indefinida o explota. `meses <= 0` devuelve NaN, nunca inf.
    """
    ini = pd.Series(saldo_inicial).astype("float64")
    fin = pd.Series(saldo_final).astype("float64")
    m = pd.Series(meses).astype("float64").mask(lambda s: s <= 0)
    return (fin - ini) * 12.0 / m


def split_backtesting_temporal(panel: pd.DataFrame, col_mes: str,
                               n_meses_validacion: int | None = None):
    """Split temporal: primeros N−k meses para entrenar, últimos k para validar.

    El split es TEMPORAL, no aleatorio: un split aleatorio dejaría meses futuros
    en el entrenamiento y el backtest no mediría nada.
    """
    k = config.MESES_VALIDACION_BACKTEST if n_meses_validacion is None else n_meses_validacion
    meses = np.sort(pd.Series(panel[col_mes]).unique())
    if len(meses) <= k:
        raise ValueError(
            f"historia insuficiente: {len(meses)} meses disponibles, "
            f"se necesitan más de {k} para dejar {k} de validación"
        )
    corte = meses[-k]
    train = panel[panel[col_mes] < corte]
    valid = panel[panel[col_mes] >= corte]
    return train, valid


def mae_mape(y_real, y_pred, eps: float = 1.0) -> dict:
    """MAE y MAPE (SPEC_V2 §6.3.4).

    El MAPE excluye los casos con |real| <= eps: con saldos que valen 0 el
    porcentaje de error es indefinido y una sola fila lo llevaría a infinito.
    Se reporta `n_mape` para que quede claro sobre cuántos casos se calculó.
    """
    real = np.asarray(y_real, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(real) & np.isfinite(pred)
    if not ok.any():
        return {"mae": float("nan"), "mape": float("nan"), "n": 0, "n_mape": 0}

    real_ok, pred_ok = real[ok], pred[ok]
    mae = float(np.mean(np.abs(real_ok - pred_ok)))

    denom = np.abs(real_ok)
    validos = denom > eps
    mape = (float(np.mean(np.abs((real_ok[validos] - pred_ok[validos]) / denom[validos])))
            if validos.any() else float("nan"))
    return {"mae": mae, "mape": mape, "n": int(ok.sum()), "n_mape": int(validos.sum())}


def escenarios_desde_errores(predicciones, errores, p_bajo: float = 25,
                             p_alto: float = 75) -> pd.DataFrame:
    """Tres escenarios a partir de la distribución empírica del error de backtest.

    Convención de signo: error = real − predicho. El escenario conservador suma
    el percentil bajo del error (típicamente negativo) y el optimista el alto.
    """
    pred = pd.Series(predicciones).astype("float64")
    err = np.asarray(errores, dtype=float)
    err = err[np.isfinite(err)]
    if err.size == 0:
        lo = hi = 0.0
    else:
        lo = float(np.percentile(err, p_bajo))
        hi = float(np.percentile(err, p_alto))

    return pd.DataFrame({
        "conservador": pred + lo,
        "base": pred,
        "optimista": pred + hi,
    }, index=pred.index)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_monto.py -v
```
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/monto.py tests/test_monto.py
git commit -m "✨feat: add 12-month amount model primitives with temporal backtest (SPEC_V2 6.3)"
```

---

## Task 20 [NUEVO]: `notebooks/06_monto_12m.ipynb` (SPEC_V2 §6.3)

Notebook — verificación de salida. **Esta es la tarea que el plan v1 dejó bloqueada (Task 18); §6.3 la desbloquea.**

**Files:**
- Create: `notebooks/06_monto_12m.ipynb`

**Interfaces:**
- Consumes: `saldos_mensual_plata` (Task 7), `cliente_features`, `fact_cliente_score` (Task 18), `src.monto.*`, `src.niveles.asignar_niveles_por_poblacion`, `src.features_modelo.features_modelo_b`.
- Produces:
  - `fact_cliente_score` en `oro.db` **actualizada** con `monto_conservador_12m, monto_base_12m, monto_optimista_12m` (TOTAL), `monto_app_12m_conservador, monto_app_12m_base, monto_app_12m_optimista` (D5, componente app: Invesbot + Inversión Virtual), `monto_prod_conservadores_12m_conservador, monto_prod_conservadores_12m_base, monto_prod_conservadores_12m_optimista` (D5, componente productos conservadores: CDT + Fiducuenta), `tiene_historial_inversion`, y los niveles de la población con historial recalculados por `valor_esperado = score × monto_base_12m` (TOTAL).
  - `outputs/models/metricas_monto.json` — `{mae, mape, n, n_mape, n_meses_historia, n_meses_validacion, n_clientes_con_historial, componentes: {app: {...}, prod_conservadores: {...}}}`
  - `outputs/models/monto_12m_app.pkl`, `outputs/models/monto_12m_prod_conservadores.pkl`

**Diseño de la descomposición (D5):** se entrenan **dos regresiones independientes**, una por componente, en vez de una sola sobre el total y luego repartir proporcionalmente. Las dos comparten la MISMA ventana temporal por cliente (`mes_ini`/`mes_fin`/`meses`, calculada una única vez sobre el saldo TOTAL) para que `total = app + productos_conservadores` sea una suma exacta y no una aproximación — si cada componente calculara su propia ventana, un cliente que empezó en CDT antes que en Invesbot tendría ventanas distintas por componente y la suma dejaría de cuadrar con el total.

- [ ] **Step 1: Celda 0 — población con historial de inversión y panel ancho por componente**

```python
import json
import sys
sys.path.insert(0, "..")

import joblib
import numpy as np
import pandas as pd

import config
from src.db_io import escribir_tabla_sqlite, leer_tabla_sqlite
from src.features_modelo import features_modelo_b
from src.monto import (
    crecimiento_anualizado, escenarios_desde_errores, mae_mape,
    split_backtesting_temporal,
)
from src.niveles import asignar_niveles_por_poblacion

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
panel = leer_tabla_sqlite(config.PLATA_DB, "saldos_mensual_plata")
panel["mes"] = pd.to_datetime(panel["mes"])

# SPEC_V2 §6.3: aplica ÚNICAMENTE a clientes con historial en productos de
# inversión (Invesbot, Inversión Virtual, CDT o Fiducuenta) con saldo > 0 en
# algún momento — la POBLACIÓN se define sobre el total de los 4 productos,
# sin cambios respecto al borrador anterior.
# D5: el RESULTADO se reporta descompuesto en dos componentes:
#   app                = Invesbot + Inversión Virtual (comportamiento tipo App)
#   prod_conservadores = CDT + Fiducuenta (saldos que podrían migrar a la App)
COMPONENTES = {
    "app": ["invesbot", "inversion_virtual"],
    "prod_conservadores": ["cdt", "fiducuenta"],
}
PRODUCTOS_INVERSION = COMPONENTES["app"] + COMPONENTES["prod_conservadores"]

panel_inv = panel[panel["producto"].isin(PRODUCTOS_INVERSION)]

# Panel ANCHO cliente-mes: una columna de saldo por componente + el total,
# para que "total" y "suma de componentes" sean la misma cifra por construcción.
panel_comp = (
    panel_inv.assign(componente=panel_inv["producto"].map(
        {p: c for c, ps in COMPONENTES.items() for p in ps}))
    .groupby(["numero_id", "mes", "componente"], as_index=False)["saldo_mes"].sum()
    .pivot(index=["numero_id", "mes"], columns="componente", values="saldo_mes")
    .fillna(0.0)
    .reset_index()
)
for c in COMPONENTES:
    if c not in panel_comp.columns:
        panel_comp[c] = 0.0
panel_comp["saldo_invertido"] = panel_comp[list(COMPONENTES)].sum(axis=1)

con_historial = set(
    panel_comp.loc[panel_comp["saldo_invertido"] > 0, "numero_id"].unique())
panel_comp = panel_comp[panel_comp["numero_id"].isin(con_historial)]

meses_disponibles = np.sort(panel_comp["mes"].unique())
print(f"clientes con historial de inversión: {len(con_historial):,}")
print(f"meses de historia: {len(meses_disponibles)} "
      f"({meses_disponibles[0].astype('datetime64[D]')} -> {meses_disponibles[-1].astype('datetime64[D]')})")
print(f"filas del panel ancho: {len(panel_comp):,}")
```

- [ ] **Step 2: Celda 1 — ventana compartida y target por componente (§6.3.2, D5)**

```python
def construir_ventana(panel_saldo):
    """mes_ini/mes_fin/meses por cliente, calculados UNA VEZ sobre el panel
    (total). Los dos componentes reutilizan esta MISMA ventana (D5) para que
    la descomposición sea aditiva: total = app + productos_conservadores."""
    agg = panel_saldo.groupby("numero_id").agg(
        mes_ini=("mes", "min"), mes_fin=("mes", "max"))
    agg["meses"] = ((agg["mes_fin"].dt.year - agg["mes_ini"].dt.year) * 12
                    + (agg["mes_fin"].dt.month - agg["mes_ini"].dt.month))
    return agg.reset_index()


def construir_target_componente(panel_ancho, col_saldo, ventana):
    """Crecimiento anualizado de UN componente, evaluado en la ventana
    compartida (mes_ini/mes_fin del TOTAL). Si el componente aún no existía en
    mes_ini (p.ej. el cliente empezó por CDT y todavía no tenía Invesbot), su
    saldo en ese mes es 0 — consistente con "sin registro = saldo 0"."""
    ini = panel_ancho.merge(ventana[["numero_id", "mes_ini"]], on="numero_id")
    ini = ini.loc[ini["mes"] == ini["mes_ini"]].set_index("numero_id")[col_saldo]
    fin = panel_ancho.merge(ventana[["numero_id", "mes_fin"]], on="numero_id")
    fin = fin.loc[fin["mes"] == fin["mes_fin"]].set_index("numero_id")[col_saldo]

    r = ventana.set_index("numero_id").copy()
    r["saldo_ini"] = ini.reindex(r.index).fillna(0.0)
    r["saldo_fin"] = fin.reindex(r.index).fillna(0.0)
    r["crecimiento_12m"] = crecimiento_anualizado(
        r["saldo_ini"], r["saldo_fin"], r["meses"]).to_numpy()
    return r.reset_index()


# §6.3.4: backtesting temporal — entrenar con los primeros N−3 meses, validar
# contra los últimos 3. El split es sobre el panel ancho (misma columna "mes").
panel_train, panel_valid = split_backtesting_temporal(
    panel_comp, "mes", n_meses_validacion=config.MESES_VALIDACION_BACKTEST)

ventana_train = construir_ventana(panel_train)
ventana_full = construir_ventana(panel_comp)

targets_train = {c: construir_target_componente(panel_train, c, ventana_train)
                 for c in COMPONENTES}
targets_full = {c: construir_target_componente(panel_comp, c, ventana_full)
                for c in COMPONENTES}

print(f"train: {panel_train['mes'].nunique()} meses hasta {panel_train['mes'].max().date()}")
print(f"valid: {panel_valid['mes'].nunique()} meses desde {panel_valid['mes'].min().date()}")
for c in COMPONENTES:
    print(f"\n{c} — crecimiento_12m:")
    print(targets_full[c]["crecimiento_12m"].describe().to_string())
```

- [ ] **Step 3: Celda 2 — una regresión y un backtest POR COMPONENTE (§6.3.3, §6.3.4, D5)**

```python
from sklearn.ensemble import HistGradientBoostingRegressor

# §6.3.3: predictoras = saldo actual + tendencia histórica (del PROPIO
# componente) + capacidad financiera.
cols_capacidad = features_modelo_b(df.columns)
base_feats = df[["numero_id"] + cols_capacidad]


def matriz(target_df, columnas_referencia=None):
    X = target_df[["numero_id", "saldo_fin", "meses"]].rename(
        columns={"saldo_fin": "saldo_invertido_actual"})
    X["tendencia_invertida"] = (
        (target_df["saldo_fin"] - target_df["saldo_ini"]) / target_df["meses"].replace(0, np.nan))
    X = X.merge(base_feats, on="numero_id", how="left").reset_index(drop=True)
    ids = X.pop("numero_id")
    X = pd.get_dummies(
        X, columns=[c for c in ["desc_segmento", "grupo_edad", "desc_tipo_de_vivienda"]
                    if c in X.columns], dummy_na=False)
    if columnas_referencia is not None:
        X = X.reindex(columns=columnas_referencia, fill_value=False)
    return ids, X


def entrenar_y_backtest(nombre_componente):
    target_train = targets_train[nombre_componente]
    ids_tr, X_tr = matriz(target_train)
    y_tr = target_train["crecimiento_12m"].reset_index(drop=True)
    ok_tr = y_tr.notna().to_numpy()

    modelo = HistGradientBoostingRegressor(random_state=config.RANDOM_STATE)
    modelo.fit(X_tr[ok_tr], y_tr[ok_tr])

    # Backtest: crecimiento OBSERVADO del componente en los meses de
    # validación, reescalado a 12 meses para ser comparable con el target.
    obs_valid = (panel_valid.sort_values("mes")
                 .groupby("numero_id")[nombre_componente].agg(["first", "last"]))
    n_meses_valid = max(panel_valid["mes"].nunique() - 1, 1)
    real_valid = crecimiento_anualizado(
        obs_valid["first"], obs_valid["last"],
        pd.Series(n_meses_valid, index=obs_valid.index))

    mask_bt = ok_tr & ids_tr.isin(real_valid.index).to_numpy()
    pred_valid = pd.Series(modelo.predict(X_tr[mask_bt]), index=ids_tr[mask_bt].to_numpy())
    real_alineado = real_valid.reindex(pred_valid.index)

    metricas = mae_mape(real_alineado.to_numpy(), pred_valid.to_numpy())
    return modelo, X_tr.columns, pred_valid, real_alineado, metricas


modelos, columnas_ref, preds_valid, reales_valid, metricas_comp = {}, {}, {}, {}, {}
for nombre in COMPONENTES:
    m, cols_ref, pv, rv, met = entrenar_y_backtest(nombre)
    modelos[nombre], columnas_ref[nombre] = m, cols_ref
    preds_valid[nombre], reales_valid[nombre] = pv, rv
    metricas_comp[nombre] = met
    print(f"{nombre} — BACKTEST: MAE={met['mae']:,.0f} | MAPE={met['mape']:.2%} "
          f"(sobre {met['n_mape']:,} clientes)")

# El backtest del TOTAL es la suma exacta de los dos componentes (misma
# ventana, mismos clientes): no se entrena un tercer modelo para el total.
idx_comun = preds_valid["app"].index.intersection(preds_valid["prod_conservadores"].index)
pred_valid_total = (preds_valid["app"].reindex(idx_comun)
                    + preds_valid["prod_conservadores"].reindex(idx_comun))
real_valid_total = (reales_valid["app"].reindex(idx_comun)
                    + reales_valid["prod_conservadores"].reindex(idx_comun))
metricas_total = mae_mape(real_valid_total.to_numpy(), pred_valid_total.to_numpy())
metricas_total["n_meses_historia"] = int(len(meses_disponibles))
metricas_total["n_meses_validacion"] = int(config.MESES_VALIDACION_BACKTEST)
metricas_total["n_clientes_con_historial"] = int(len(con_historial))
metricas_total["componentes"] = metricas_comp
print(f"\nTOTAL (app + productos_conservadores) — BACKTEST: "
      f"MAE={metricas_total['mae']:,.0f} | MAPE={metricas_total['mape']:.2%}")
```

- [ ] **Step 4: Celda 3 — tres escenarios por componente + total, y limitación documentada (§6.3.5, D5)**

```python
preds_full, escenarios_comp = {}, {}
for nombre in COMPONENTES:
    ids_full, X_full = matriz(targets_full[nombre], columnas_referencia=columnas_ref[nombre])
    pred_full = pd.Series(modelos[nombre].predict(X_full), index=ids_full.to_numpy())
    preds_full[nombre] = pred_full

    errores = (reales_valid[nombre] - preds_valid[nombre]).dropna().to_numpy()
    esc = escenarios_desde_errores(pred_full, errores)
    esc.columns = [f"monto_{nombre}_12m_conservador" if c == "conservador"
                   else f"monto_{nombre}_12m_optimista" if c == "optimista"
                   else f"monto_{nombre}_12m_base" for c in esc.columns]
    esc["numero_id"] = pred_full.index
    escenarios_comp[nombre] = esc

# Total = suma de los dos componentes en cada escenario (D5: "el export a
# Power BI debe incluir ambas columnas ADEMÁS del total").
esc_total = escenarios_comp["app"].merge(
    escenarios_comp["prod_conservadores"], on="numero_id", how="outer").fillna(0.0)
esc_total["monto_conservador_12m"] = (
    esc_total["monto_app_12m_conservador"] + esc_total["monto_prod_conservadores_12m_conservador"])
esc_total["monto_base_12m"] = (
    esc_total["monto_app_12m_base"] + esc_total["monto_prod_conservadores_12m_base"])
esc_total["monto_optimista_12m"] = (
    esc_total["monto_app_12m_optimista"] + esc_total["monto_prod_conservadores_12m_optimista"])

for nombre, modelo in modelos.items():
    joblib.dump(modelo, config.OUTPUTS_DIR / "models" / f"monto_12m_{nombre}.pkl")
with open(config.OUTPUTS_DIR / "models" / "metricas_monto.json", "w") as f:
    json.dump(metricas_total, f, indent=2)

print(esc_total[["monto_conservador_12m", "monto_base_12m", "monto_optimista_12m",
                 "monto_app_12m_base", "monto_prod_conservadores_12m_base"]]
      .describe().to_string())
print(
    "\n" + "=" * 78 + "\n"
    "SPEC_V2 §6.3 — LIMITACIÓN A DOCUMENTAR EXPLÍCITAMENTE\n"
    + "=" * 78 + "\n"
    f"Con {len(meses_disponibles)} meses de historia NO es posible validar un horizonte "
    "de 12 meses de forma rigurosa ni capturar estacionalidad anual.\n"
    f"El resultado es una EXTRAPOLACIÓN validada únicamente contra un horizonte de "
    f"{config.MESES_VALIDACION_BACKTEST} meses "
    f"(MAE total={metricas_total['mae']:,.0f}, MAPE total={metricas_total['mape']:.1%}).\n"
    "Reportar SIEMPRE como rango [conservador, optimista], NUNCA como cifra única.\n"
    "\nD5 — DESCOMPOSICIÓN: 'app' (Invesbot + Inversión Virtual) es crecimiento en "
    "comportamiento autogestionado, el más análogo a la nueva App; "
    "'productos_conservadores' (CDT + Fiducuenta) es migración potencial de saldos "
    "existentes bajo el supuesto de que ese saldo PODRÍA trasladarse a la App — no es "
    "un hecho, es un techo de oportunidad. Ambas cifras tienen implicaciones de "
    "negocio distintas y se reportan por separado, nunca solo el total.\n"
    "\nRegularización: forward fill (un saldo persiste hasta el siguiente movimiento). "
    "NO se interpoló linealmente: interpolar inventaría movimientos intermedios."
)
```

- [ ] **Step 5: Celda 4 — actualizar `fact_cliente_score` y recalcular niveles (§6.2)**

```python
fact = leer_tabla_sqlite(config.ORO_DB, "fact_cliente_score")
fact = fact.merge(esc_total, on="numero_id", how="left")

fact["tiene_historial_inversion"] = fact["numero_id"].isin(con_historial).astype(int)

# SPEC_V2 §6.3: los clientes sin historial reciben monto NULL. NO imputar cero:
# no es cero, es desconocido. Aplica al total Y a los dos componentes.
sin_hist_inv = fact["tiene_historial_inversion"] == 0
cols_monto = (
    ["monto_conservador_12m", "monto_base_12m", "monto_optimista_12m"]
    + [f"monto_{c}_12m_{esc}" for c in ["app", "prod_conservadores"]
       for esc in ["conservador", "base", "optimista"]]
)
for c in cols_monto:
    fact.loc[sin_hist_inv, c] = np.nan

# §6.2: la población con historial se ordena por valor_esperado = score × monto TOTAL
fact["valor_esperado_12m"] = fact["score"] * fact["monto_base_12m"]
con_hist = fact["poblacion"] == "con_historial"
fact.loc[con_hist, "valor_referencia"] = fact.loc[con_hist, "valor_esperado_12m"]
fact.loc[con_hist, "tipo_valor_referencia"] = "valor_esperado_score_x_monto_12m"
# Los que tienen producto pero no historial de inversión no tienen monto:
# se ordenan por score dentro de su misma población.
sin_monto = con_hist & fact["valor_esperado_12m"].isna()
fact.loc[sin_monto, "valor_referencia"] = fact.loc[sin_monto, "score"]

fact["nivel"] = asignar_niveles_por_poblacion(fact, "valor_referencia", "poblacion")
escribir_tabla_sqlite(fact, config.ORO_DB, "fact_cliente_score")

print(pd.crosstab(fact["poblacion"], fact["nivel"]).to_string())
print(f"\ncon monto estimado: {int(fact['monto_base_12m'].notna().sum()):,}")
print(f"sin monto (NULL, no cero): {int(fact['monto_base_12m'].isna().sum()):,}")
```

- [ ] **Step 6: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/06_monto_12m.ipynb
```
Expected: exit code 0.

- [ ] **Step 7: Verificar**

```bash
python -c "
import json
import numpy as np
import config
from src.db_io import leer_tabla_sqlite

with open(config.OUTPUTS_DIR / 'models' / 'metricas_monto.json') as f:
    m = json.load(f)
assert m['mae'] >= 0 and m['n'] > 0, m
assert m['n_meses_validacion'] == 3
assert {'app', 'prod_conservadores'} <= set(m['componentes'])

f = leer_tabla_sqlite(config.ORO_DB, 'fact_cliente_score')
cols_monto = {'monto_conservador_12m','monto_base_12m','monto_optimista_12m',
              'monto_app_12m_conservador','monto_app_12m_base','monto_app_12m_optimista',
              'monto_prod_conservadores_12m_conservador','monto_prod_conservadores_12m_base',
              'monto_prod_conservadores_12m_optimista','tiene_historial_inversion'}
assert cols_monto <= set(f.columns), cols_monto - set(f.columns)

# SPEC_V2 §6.3: sin historial -> NULL, nunca 0 imputado (total y componentes)
sin = f[f['tiene_historial_inversion'] == 0]
assert sin['monto_base_12m'].isna().all(), 'se imputó monto a clientes sin historial'
assert sin['monto_app_12m_base'].isna().all()
con = f[f['tiene_historial_inversion'] == 1]
assert con['monto_base_12m'].notna().all()

# los escenarios son un rango ordenado, para el total y para cada componente
ok = con['monto_base_12m'].notna()
assert (con.loc[ok,'monto_conservador_12m'] <= con.loc[ok,'monto_base_12m']).all()
assert (con.loc[ok,'monto_base_12m'] <= con.loc[ok,'monto_optimista_12m']).all()
assert (con.loc[ok,'monto_app_12m_conservador'] <= con.loc[ok,'monto_app_12m_base']).all()
assert (con.loc[ok,'monto_app_12m_base'] <= con.loc[ok,'monto_app_12m_optimista']).all()

# D5: el total debe ser exactamente la suma de los dos componentes
suma = con.loc[ok,'monto_base_12m'] - (con.loc[ok,'monto_app_12m_base']
                                        + con.loc[ok,'monto_prod_conservadores_12m_base'])
assert (suma.abs() < 1e-6).all(), 'D5: total != app + productos_conservadores'

# ningún cliente perdió su score
assert f['score'].notna().all()
print(f'OK §6.3/D5 — MAE total={m[\"mae\"]:,.0f} MAPE total={m[\"mape\"]:.1%} | '
      f'{len(con):,} con monto, {len(sin):,} en NULL | total=app+productos_conservadores verificado')
"
```
Expected: `OK §6.3/D5 — MAE total=... MAPE total=...% | <N> con monto, <M> en NULL | total=app+productos_conservadores verificado`

- [ ] **Step 8: Commit**

```bash
git add notebooks/06_monto_12m.ipynb
git commit -m "✨feat: add 12-month amount model decomposed into app vs conservative products (SPEC_V2 6.3, D5)"
```

---

## Task 21 [NUEVO]: `src/auditoria_sesgo.py` — regla del 80% (SPEC_V2 §6.6)

**Files:**
- Create: `tests/test_auditoria_sesgo.py`
- Create: `src/auditoria_sesgo.py`

**Interfaces:**
- Produces:
  - `tasa_seleccion_por_grupo(df, col_grupo, col_nivel, nivel_objetivo="A") -> pd.DataFrame` con `grupo, n, n_seleccionados, tasa_seleccion`
  - `razon_impacto_dispar(tasas) -> float` (min/max)
  - `cumple_regla_80(razon, umbral=0.8) -> bool`
  - `diferencia_score_por_grupo(df, col_grupo, col_score) -> pd.DataFrame` con `grupo, n, score_medio, p_valor_vs_resto`
  - Consumidas por `notebooks/07_auditoria_sesgo.ipynb` (Task 22).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_auditoria_sesgo.py
import numpy as np
import pandas as pd
import pytest

from src.auditoria_sesgo import (
    cumple_regla_80,
    diferencia_score_por_grupo,
    razon_impacto_dispar,
    tasa_seleccion_por_grupo,
)


def test_tasa_seleccion_por_grupo():
    df = pd.DataFrame({
        "desc_genero": ["M"] * 10 + ["F"] * 10,
        "nivel": ["A"] * 5 + ["B"] * 5 + ["A"] * 2 + ["C"] * 8,
    })
    r = tasa_seleccion_por_grupo(df, "desc_genero", "nivel").set_index("grupo")
    assert r.loc["M", "tasa_seleccion"] == 0.5
    assert r.loc["F", "tasa_seleccion"] == 0.2
    assert r.loc["M", "n"] == 10
    assert r.loc["M", "n_seleccionados"] == 5


def test_tasa_seleccion_incluye_grupos_sin_seleccionados():
    df = pd.DataFrame({"g": ["x", "y"], "nivel": ["A", "D"]})
    r = tasa_seleccion_por_grupo(df, "g", "nivel").set_index("grupo")
    assert r.loc["y", "tasa_seleccion"] == 0.0


def test_tasa_seleccion_trata_nulos_como_grupo():
    df = pd.DataFrame({"g": ["x", None], "nivel": ["A", "A"]})
    r = tasa_seleccion_por_grupo(df, "g", "nivel")
    assert len(r) == 2


def test_razon_impacto_dispar_es_min_sobre_max():
    assert razon_impacto_dispar({"M": 0.10, "F": 0.075}) == pytest.approx(0.75)
    assert razon_impacto_dispar({"M": 0.10, "F": 0.10}) == pytest.approx(1.0)


def test_razon_con_maximo_cero_es_nan():
    assert np.isnan(razon_impacto_dispar({"a": 0.0, "b": 0.0}))


def test_regla_80():
    """SPEC_V2 §6.6.2: por debajo de 0.8 se reporta explícitamente como hallazgo."""
    assert cumple_regla_80(0.81) is True
    assert cumple_regla_80(0.80) is True
    assert cumple_regla_80(0.79) is False


def test_diferencia_score_por_grupo_detecta_brecha():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "g": ["a"] * 500 + ["b"] * 500,
        "score": np.concatenate([rng.normal(0.30, 0.05, 500),
                                 rng.normal(0.10, 0.05, 500)]),
    })
    r = diferencia_score_por_grupo(df, "g", "score").set_index("grupo")
    assert r.loc["a", "score_medio"] > r.loc["b", "score_medio"]
    assert r.loc["a", "p_valor_vs_resto"] < 0.001


def test_diferencia_score_grupo_unico_devuelve_nan():
    df = pd.DataFrame({"g": ["a", "a"], "score": [0.1, 0.2]})
    r = diferencia_score_por_grupo(df, "g", "score")
    assert np.isnan(r.loc[0, "p_valor_vs_resto"])
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_auditoria_sesgo.py -v
```
Expected: FAIL con `ModuleNotFoundError: No module named 'src.auditoria_sesgo'`

- [ ] **Step 3: Implementar `src/auditoria_sesgo.py`**

```python
# src/auditoria_sesgo.py
"""Auditoría de sesgo del modelo (SPEC_V2 §6.6).

Se ejecuta con independencia de qué variables entren al modelo: excluir una
variable de la lista de entrada no la excluye del modelo si otras la codifican.
"""
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

ETIQUETA_NULOS = "Sin dato"


def tasa_seleccion_por_grupo(df: pd.DataFrame, col_grupo: str, col_nivel: str,
                             nivel_objetivo: str = "A") -> pd.DataFrame:
    """Proporción de cada grupo que llega al nivel objetivo (SPEC_V2 §6.6.2)."""
    g = pd.Series(df[col_grupo]).astype(object)
    g = g.where(g.notna(), ETIQUETA_NULOS)
    sel = (df[col_nivel] == nivel_objetivo).astype(int)

    r = (
        pd.DataFrame({"grupo": g, "sel": sel})
        .groupby("grupo", as_index=False)["sel"]
        .agg(n="count", n_seleccionados="sum")
    )
    r["tasa_seleccion"] = r["n_seleccionados"] / r["n"]
    return r


def razon_impacto_dispar(tasas) -> float:
    """Razón entre el grupo menos y el más favorecido (regla del 80%)."""
    s = pd.Series(tasas, dtype="float64").dropna()
    if s.empty or s.max() == 0:
        return float("nan")
    return float(s.min() / s.max())


def cumple_regla_80(razon: float, umbral: float = 0.8) -> bool:
    """False => hallazgo a reportar explícitamente (SPEC_V2 §6.6.2)."""
    if razon is None or (isinstance(razon, float) and np.isnan(razon)):
        return False
    return bool(razon >= umbral)


def diferencia_score_por_grupo(df: pd.DataFrame, col_grupo: str,
                               col_score: str) -> pd.DataFrame:
    """Score medio por grupo y significancia frente al resto (SPEC_V2 §6.6.3).

    Mann-Whitney y no t-test: la distribución de scores es fuertemente asimétrica.
    """
    g = pd.Series(df[col_grupo]).astype(object)
    g = g.where(g.notna(), ETIQUETA_NULOS)
    score = pd.Series(df[col_score]).astype("float64")

    filas = []
    for grupo in sorted(g.dropna().unique(), key=str):
        dentro = score[(g == grupo) & score.notna()]
        fuera = score[(g != grupo) & score.notna()]
        if len(dentro) == 0 or len(fuera) == 0:
            p = float("nan")
        else:
            p = float(mannwhitneyu(dentro, fuera, alternative="two-sided").pvalue)
        filas.append({
            "grupo": grupo,
            "n": int(len(dentro)),
            "score_medio": float(dentro.mean()) if len(dentro) else float("nan"),
            "score_mediano": float(dentro.median()) if len(dentro) else float("nan"),
            "p_valor_vs_resto": p,
        })
    return pd.DataFrame(filas)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_auditoria_sesgo.py -v
```
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/auditoria_sesgo.py tests/test_auditoria_sesgo.py
git commit -m "✨feat: add bias audit primitives - 80% rule and score gap tests (SPEC_V2 6.6)"
```

---

## Task 22 [NUEVO]: `notebooks/07_auditoria_sesgo.ipynb` (SPEC_V2 §6.6)

Notebook — verificación de salida.

**Files:**
- Create: `notebooks/07_auditoria_sesgo.ipynb`

**Interfaces:**
- Consumes: `cliente_features`, `fact_cliente_score`, `src.auditoria_sesgo.*`, `src.features_modelo.features_modelo_a`, `src.decisiones.decidir_interpretacion_proxy_genero` (D6).
- Produces: `outputs/powerbi/fact_auditoria_sesgo.csv` — `atributo, grupo, n, tasa_seleccion_nivel_A, razon_impacto_dispar, cumple_regla_80, score_medio, p_valor_vs_resto, auc_proxy_genero, interpretacion_proxy_genero` y `outputs/models/proxy_genero.json`.

- [ ] **Step 1: Celda 0 — prueba de proxy para género (§6.6.1)**

```python
import json
import sys
sys.path.insert(0, "..")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

import config
from src.auditoria_sesgo import (
    cumple_regla_80, diferencia_score_por_grupo,
    razon_impacto_dispar, tasa_seleccion_por_grupo,
)
from src.db_io import leer_tabla_sqlite
from src.decisiones import decidir_interpretacion_proxy_genero
from src.features_modelo import features_modelo_a

df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
fact = leer_tabla_sqlite(config.ORO_DB, "fact_cliente_score")
datos = df.merge(fact[["numero_id", "score", "nivel", "poblacion", "modelo_usado"]],
                 on="numero_id", how="inner")
(config.OUTPUTS_DIR / "powerbi").mkdir(parents=True, exist_ok=True)

# §6.6.1: ¿el género se filtra por variables correlacionadas?
# Si el AUC es alto, excluir desc_genero de la lista de entrada NO lo excluye del modelo.
con_genero = datos[datos["desc_genero"].notna()].reset_index(drop=True)
generos = con_genero["desc_genero"].value_counts()
print(generos.to_string())

principal = generos.index[0]
y_genero = (con_genero["desc_genero"] == principal).astype(int)
cols = features_modelo_a(con_genero.columns)
X_g = pd.get_dummies(
    con_genero[cols],
    columns=[c for c in ["desc_segmento", "grupo_edad", "desc_tipo_de_vivienda"] if c in cols],
    dummy_na=False,
)

Xg_tr, Xg_te, yg_tr, yg_te = train_test_split(
    X_g, y_genero, test_size=config.TEST_SIZE,
    random_state=config.RANDOM_STATE, stratify=y_genero)
proxy = HistGradientBoostingClassifier(random_state=config.RANDOM_STATE)
proxy.fit(Xg_tr, yg_tr)
auc_proxy = float(roc_auc_score(yg_te, proxy.predict_proba(Xg_te)[:, 1]))

sub = Xg_te.sample(n=min(30_000, len(Xg_te)), random_state=config.RANDOM_STATE)
pi = permutation_importance(proxy, sub, yg_te.loc[sub.index], n_repeats=5,
                            random_state=config.RANDOM_STATE, scoring="roc_auc")
top_proxy = (pd.DataFrame({"variable": sub.columns, "importancia": pi.importances_mean})
             .sort_values("importancia", ascending=False).head(10).reset_index(drop=True))

# D6: bandas de interpretación en vez de un umbral único — un umbral binario
# oculta el caso intermedio, que es el resultado más probable.
interpretacion_proxy = decidir_interpretacion_proxy_genero(auc_proxy)
print(f"\nAUC del clasificador de género a partir del resto de predictoras: {auc_proxy:.4f}")
print(f"Interpretación (D6): {interpretacion_proxy['interpretacion']} "
      f"-> acción: {interpretacion_proxy['accion']}")
print("\nVariables más asociadas al género:")
print(top_proxy.to_string(index=False))

with open(config.OUTPUTS_DIR / "models" / "proxy_genero.json", "w", encoding="utf-8") as f:
    json.dump({**interpretacion_proxy,
               "umbral_moderado": config.UMBRAL_AUC_PROXY_MODERADO,
               "umbral_sustancial": config.UMBRAL_AUC_PROXY_SUSTANCIAL,
               "variables_mas_asociadas": top_proxy.to_dict(orient="records")},
              f, indent=2, ensure_ascii=False)
```

- [ ] **Step 2: Celda 1 — impacto dispar (§6.6.2) y diferencia de score (§6.6.3)**

```python
ATRIBUTOS = ["desc_genero", "grupo_edad", "desc_tipo_de_vivienda"]

filas = []
for atributo in ATRIBUTOS:
    tasas = tasa_seleccion_por_grupo(datos, atributo, "nivel", nivel_objetivo="A")
    razon = razon_impacto_dispar(tasas.set_index("grupo")["tasa_seleccion"])
    cumple = cumple_regla_80(razon, umbral=config.UMBRAL_IMPACTO_DISPAR)
    scores = diferencia_score_por_grupo(datos, atributo, "score")

    t = tasas.merge(scores[["grupo", "score_medio", "score_mediano", "p_valor_vs_resto"]],
                    on="grupo", how="left")
    t.insert(0, "atributo", atributo)
    t["razon_impacto_dispar"] = razon
    t["cumple_regla_80"] = cumple
    filas.append(t)

    estado = "OK" if cumple else "HALLAZGO — por debajo de 0.8"
    print(f"\n=== {atributo} — razón de impacto dispar = {razon:.3f} [{estado}] ===")
    print(t[["grupo", "n", "tasa_seleccion", "score_medio", "p_valor_vs_resto"]]
          .to_string(index=False))

auditoria = pd.concat(filas, ignore_index=True)
auditoria["auc_proxy_genero"] = auc_proxy
auditoria["interpretacion_proxy_genero"] = interpretacion_proxy["interpretacion"]
auditoria.rename(columns={"tasa_seleccion": "tasa_seleccion_nivel_A"}, inplace=True)
auditoria.to_csv(config.OUTPUTS_DIR / "powerbi" / "fact_auditoria_sesgo.csv", index=False)
```

- [ ] **Step 3: Celda 2 — precaución específica para `grupo_edad` (§6.4)**

```python
# SPEC_V2 §6.4: verificar que el modelo no excluya sistemáticamente a los grupos
# de mayor edad. La adopción digital correlaciona con edad y existe el riesgo de
# estar prediciendo "usa aplicaciones" en vez de "quiere invertir".
edad = auditoria[auditoria["atributo"] == "grupo_edad"].sort_values("grupo")
print("Tasa de selección al nivel A por grupo de edad:")
print(edad[["grupo", "n", "tasa_seleccion_nivel_A", "score_medio"]].to_string(index=False))

peor = edad.loc[edad["tasa_seleccion_nivel_A"].idxmin()]
mejor = edad.loc[edad["tasa_seleccion_nivel_A"].idxmax()]
print(f"\nGrupo menos favorecido: {peor['grupo']} ({peor['tasa_seleccion_nivel_A']:.2%})")
print(f"Grupo más favorecido:  {mejor['grupo']} ({mejor['tasa_seleccion_nivel_A']:.2%})")
print(f"Razón: {edad['razon_impacto_dispar'].iloc[0]:.3f}")

print(
    "\nSPEC_V2 §6.6 — `desc_genero` se conserva en dim_cliente EXCLUSIVAMENTE para "
    "esta auditoría y para caracterización descriptiva del tablero. Nunca como "
    "predictora (verificado por src/features_modelo.py y tests/test_features_modelo.py)."
)
```

- [ ] **Step 4: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/07_auditoria_sesgo.ipynb
```
Expected: exit code 0.

- [ ] **Step 5: Verificar**

```bash
python -c "
import json
import pandas as pd
import config

a = pd.read_csv(config.OUTPUTS_DIR / 'powerbi' / 'fact_auditoria_sesgo.csv')
req = {'atributo','grupo','n','tasa_seleccion_nivel_A','razon_impacto_dispar',
       'cumple_regla_80','score_medio','p_valor_vs_resto','auc_proxy_genero',
       'interpretacion_proxy_genero'}
assert req <= set(a.columns), req - set(a.columns)
assert set(a['atributo']) == {'desc_genero','grupo_edad','desc_tipo_de_vivienda'}
assert a['tasa_seleccion_nivel_A'].between(0,1).all()
assert a['razon_impacto_dispar'].between(0,1).all()
assert set(a['interpretacion_proxy_genero']) <= {'proxy mínimo','proxy moderado','proxy sustancial'}

with open(config.OUTPUTS_DIR / 'models' / 'proxy_genero.json', encoding='utf-8') as f:
    p = json.load(f)
assert 0.0 <= p['auc'] <= 1.0
assert len(p['variables_mas_asociadas']) == 10
# D6: la interpretación debe coincidir con la tabla de bandas, no con un umbral libre
from src.decisiones import decidir_interpretacion_proxy_genero
esperado = decidir_interpretacion_proxy_genero(p['auc'])
assert p['interpretacion'] == esperado['interpretacion'] and p['accion'] == esperado['accion']

hallazgos = a.loc[~a['cumple_regla_80'], 'atributo'].unique().tolist()
print(f'OK §6.6 — AUC proxy género={p[\"auc\"]:.4f} -> {p[\"interpretacion\"]} (D6, acción: {p[\"accion\"]})')
print(f'   atributos que NO cumplen la regla del 80%: {hallazgos or \"ninguno\"}')
"
```
Expected: `OK §6.6 — AUC proxy género=0.xxxx -> <interpretación> (D6, acción: <acción>)` + la lista de hallazgos.

- [ ] **Step 6: Commit**

```bash
git add notebooks/07_auditoria_sesgo.ipynb
git commit -m "✨feat: add bias audit notebook - gender proxy, 80% rule, score gaps (SPEC_V2 6.6)"
```

---

# FASE 6 — Esquema estrella, dimensionamiento y export

---

## Task 23 [MODIFICA]: `fact_saldos_mensual` y `dim_tiempo` mensual (SPEC_V2 §8)

**Files:**
- Modify: `oro/construir_esquema_estrella.py`
- Create: `tests/test_esquema_estrella.py`

**Interfaces:**
- Consumes: `saldos_mensual_plata` (Task 7), `clientes_plata`.
- Produces: en `oro.db` — `fact_saldos_mensual` (`numero_id, producto_id, fecha_id, mes, saldo_mes`, **grano mensual, no diario**), `dim_tiempo` (grano mes), `dim_producto`, `dim_cliente`. `fact_saldos` (snapshot) se conserva para no romper nada existente.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_esquema_estrella.py
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_esquema_estrella.py -v
```
Expected: FAIL — `fact_saldos_mensual` no existe en `oro.db`.

- [ ] **Step 3: Implementar**

Reemplazar `construir_esquema_estrella()` en `oro/construir_esquema_estrella.py`:

```python
def construir_esquema_estrella():
    clientes = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")
    # SPEC_V2 §8: dim_cliente incluye desc_genero SOLO para auditoría de sesgo y
    # caracterización descriptiva del tablero. Nunca como predictora.
    cols_dim = ["numero_id", "grupo_edad", "desc_genero", "desc_segmento",
                "desc_tipo_de_vivienda"]
    dim_cliente = clientes[[c for c in cols_dim if c in clientes.columns]]
    escribir_tabla_sqlite(dim_cliente, config.ORO_DB, "dim_cliente")

    # --- fact_saldos_mensual: grano MENSUAL (SPEC_V2 §8) ---
    mensual = leer_tabla_sqlite(config.PLATA_DB, "saldos_mensual_plata")
    mensual["mes"] = pd.to_datetime(mensual["mes"])

    dim_producto = pd.DataFrame({"producto": sorted(mensual["producto"].unique())})
    dim_producto["producto_id"] = range(1, len(dim_producto) + 1)
    escribir_tabla_sqlite(dim_producto, config.ORO_DB, "dim_producto")

    dim_tiempo = (
        mensual[["mes"]].drop_duplicates().sort_values("mes")
        .rename(columns={"mes": "fecha"}).reset_index(drop=True)
    )
    dim_tiempo["fecha_id"] = range(1, len(dim_tiempo) + 1)
    dim_tiempo["anio"] = dim_tiempo["fecha"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha"].dt.month
    dim_tiempo["trimestre"] = dim_tiempo["fecha"].dt.quarter
    escribir_tabla_sqlite(dim_tiempo, config.ORO_DB, "dim_tiempo")

    fact_saldos_mensual = (
        mensual
        .merge(dim_producto, on="producto", how="left")
        .merge(dim_tiempo[["fecha", "fecha_id"]], left_on="mes", right_on="fecha",
               how="left")
        [["numero_id", "producto_id", "fecha_id", "mes", "saldo_mes"]]
    )
    escribir_tabla_sqlite(fact_saldos_mensual, config.ORO_DB, "fact_saldos_mensual")

    # fact_saldos (snapshot cliente-producto) se conserva: alimenta las vistas
    # de "último saldo" del tablero, que no necesitan la serie mensual completa.
    fact_frames = [leer_tabla_sqlite(config.PLATA_DB, t) for t in TABLAS_PRODUCTO_LARGAS]
    fact_saldos = pd.concat(fact_frames, ignore_index=True)
    if not fact_saldos.empty:
        fact_saldos["fecha_snapshot"] = pd.to_datetime(fact_saldos["fecha_snapshot"])
        fact_saldos = fact_saldos.merge(dim_producto, on="producto", how="left")
    escribir_tabla_sqlite(fact_saldos, config.ORO_DB, "fact_saldos")

    return dim_cliente, dim_producto, dim_tiempo, fact_saldos_mensual


if __name__ == "__main__":
    dim_cliente, dim_producto, dim_tiempo, fact_mensual = construir_esquema_estrella()
    print(f"dim_cliente: {len(dim_cliente):,} | dim_producto: {len(dim_producto)} | "
          f"dim_tiempo: {len(dim_tiempo)} meses")
    print(f"fact_saldos_mensual: {len(fact_mensual):,} filas (grano mensual)")
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_esquema_estrella.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Ejecutar sobre datos reales y reportar el volumen (§8)**

```bash
python -m oro.construir_esquema_estrella
```
Expected: imprime los conteos; **anotar el de `fact_saldos_mensual`**, que SPEC_V2 §8 pide reportar.

```bash
python -c "
import config
from src.db_io import leer_tabla_sqlite
fm = leer_tabla_sqlite(config.ORO_DB, 'fact_saldos_mensual')
dt = leer_tabla_sqlite(config.ORO_DB, 'dim_tiempo')
print(f'fact_saldos_mensual: {len(fm):,} filas | dim_tiempo: {len(dt)} meses')
assert not fm.duplicated(subset=['numero_id','producto_id','fecha_id']).any()
assert fm['saldo_mes'].notna().all()
assert len(dt) <= 24, f'dim_tiempo con {len(dt)} filas: no parece grano mensual'
print('OK §8: fact_saldos_mensual con grano mensual y sin duplicados')
"
```
Expected: la línea de volumen + `OK §8: fact_saldos_mensual con grano mensual y sin duplicados`

- [ ] **Step 6: Commit**

```bash
git add oro/construir_esquema_estrella.py tests/test_esquema_estrella.py
git commit -m "✨feat: add monthly fact_saldos_mensual and monthly dim_tiempo (SPEC_V2 8)"
```

---

## Task 24 [NUEVO]: `notebooks/05_dimensionamiento.ipynb` (SPEC_V2 §7)

Notebook — verificación de salida.

**Files:**
- Create: `notebooks/05_dimensionamiento.ipynb`

**Interfaces:**
- Consumes: `fact_cliente_score` (Tasks 18 y 20), `cliente_features`.
- Produces: `outputs/powerbi/dimensionamiento.csv` (`nivel, poblacion, desc_segmento, n_clientes, monto_conservador, monto_base, monto_optimista, monto_app_base, monto_prod_conservadores_base` — D5: los dos componentes además del total) y `outputs/eda/resumen_ejecutivo.json`.

- [ ] **Step 1: Celda 0 — clientes por nivel y población**

```python
import json
import sys
sys.path.insert(0, "..")

import numpy as np
import pandas as pd

import config
from src.db_io import leer_tabla_sqlite

fact = leer_tabla_sqlite(config.ORO_DB, "fact_cliente_score")
df = leer_tabla_sqlite(config.ORO_DB, "cliente_features")
datos = fact.merge(df[["numero_id", "desc_segmento"]], on="numero_id", how="left")
(config.OUTPUTS_DIR / "powerbi").mkdir(parents=True, exist_ok=True)

por_nivel = (
    datos.groupby(["poblacion", "nivel"], as_index=False)
    .agg(n_clientes=("numero_id", "count"))
    .sort_values(["poblacion", "nivel"])
)
print("Clientes por nivel de prioridad y población:")
print(por_nivel.pivot(index="nivel", columns="poblacion", values="n_clientes").to_string())
```

- [ ] **Step 2: Celda 1 — monto agregado por nivel, tres escenarios**

```python
# SPEC_V2 §7: monto potencial agregado por nivel, en los tres escenarios,
# SOLO para la población con historial. La población sin historial no tiene
# monto: su monto es NULL, no cero (§6.3).
con_hist = datos[datos["tiene_historial_inversion"] == 1]

montos = (
    con_hist.groupby("nivel", as_index=False)
    .agg(n_clientes=("numero_id", "count"),
         monto_conservador=("monto_conservador_12m", "sum"),
         monto_base=("monto_base_12m", "sum"),
         monto_optimista=("monto_optimista_12m", "sum"),
         # D5: descomposición además del total.
         monto_app_base=("monto_app_12m_base", "sum"),
         monto_prod_conservadores_base=("monto_prod_conservadores_12m_base", "sum"))
    .sort_values("nivel")
)
print("Monto potencial agregado a 12 meses (solo población con historial de inversión):")
print(montos.to_string(index=False))
print(f"\nClientes SIN historial de inversión (monto NULL, no cero): "
      f"{int((datos['tiene_historial_inversion'] == 0).sum()):,}")
```

- [ ] **Step 3: Celda 2 — distribución de niveles por segmento**

```python
por_segmento = (
    datos.groupby(["desc_segmento", "poblacion", "nivel"], as_index=False)
    .agg(n_clientes=("numero_id", "count"))
)
tabla_seg = por_segmento.pivot_table(
    index="desc_segmento", columns="nivel", values="n_clientes",
    aggfunc="sum", fill_value=0)
print("Distribución de niveles por desc_segmento:")
print(tabla_seg.to_string())
```

- [ ] **Step 4: Celda 3 — tabla final y resumen ejecutivo**

```python
dimensionamiento = (
    datos.groupby(["nivel", "poblacion", "desc_segmento"], as_index=False)
    .agg(n_clientes=("numero_id", "count"),
         monto_conservador=("monto_conservador_12m", "sum"),
         monto_base=("monto_base_12m", "sum"),
         monto_optimista=("monto_optimista_12m", "sum"),
         # D5: descomposición del monto base (además del total) por componente.
         monto_app_base=("monto_app_12m_base", "sum"),
         monto_prod_conservadores_base=("monto_prod_conservadores_12m_base", "sum"),
         score_medio=("score", "mean"))
    .sort_values(["nivel", "poblacion", "desc_segmento"])
)
dimensionamiento.to_csv(config.OUTPUTS_DIR / "powerbi" / "dimensionamiento.csv", index=False)

priorizados = datos[datos["nivel"].isin(["A", "B"])]
resumen = {
    "n_clientes_total": int(len(datos)),
    "n_clientes_priorizados_A_B": int(len(priorizados)),
    "n_nivel_A": int((datos["nivel"] == "A").sum()),
    "n_nivel_A_con_historial": int(((datos["nivel"] == "A") &
                                    (datos["poblacion"] == "con_historial")).sum()),
    "n_nivel_A_sin_historial": int(((datos["nivel"] == "A") &
                                    (datos["poblacion"] == "sin_historial")).sum()),
    "oportunidad_12m_conservador": float(con_hist["monto_conservador_12m"].sum()),
    "oportunidad_12m_base": float(con_hist["monto_base_12m"].sum()),
    "oportunidad_12m_optimista": float(con_hist["monto_optimista_12m"].sum()),
    "n_clientes_con_monto": int(con_hist["monto_base_12m"].notna().sum()),
}
with open(config.OUTPUTS_DIR / "eda" / "resumen_ejecutivo.json", "w", encoding="utf-8") as f:
    json.dump(resumen, f, indent=2, ensure_ascii=False)

print("=" * 78)
print("RESUMEN EJECUTIVO")
print("=" * 78)
print(f"Clientes totales scoreados:            {resumen['n_clientes_total']:,}")
print(f"Clientes priorizados (niveles A y B):  {resumen['n_clientes_priorizados_A_B']:,}")
print(f"  · nivel A con historial:             {resumen['n_nivel_A_con_historial']:,}")
print(f"  · nivel A sin historial (lookalike): {resumen['n_nivel_A_sin_historial']:,}")
print(f"\nRango de oportunidad a 12 meses (población con historial, "
      f"{resumen['n_clientes_con_monto']:,} clientes):")
print(f"  conservador: {resumen['oportunidad_12m_conservador']:,.0f}")
print(f"  base:        {resumen['oportunidad_12m_base']:,.0f}")
print(f"  optimista:   {resumen['oportunidad_12m_optimista']:,.0f}")
print(
    "\nADVERTENCIAS DE INTERPRETACIÓN:\n"
    "· La cifra es un RANGO, no un pronóstico puntual: el horizonte de 12 meses se "
    "extrapola desde ~13 meses de historia, validado solo contra 3 meses (§6.3).\n"
    "· Los clientes 'A' sin historial se rankean por SIMILITUD (lookalike), no por "
    "probabilidad validada: en ese segmento la etiqueta es 0 por construcción (§6.1).\n"
    "· Los niveles NO son comparables entre poblaciones: cada 'A' es el 25% superior "
    "de SU población (§6.2)."
)
```

- [ ] **Step 5: Ejecutar el notebook**

```bash
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/05_dimensionamiento.ipynb
```
Expected: exit code 0.

- [ ] **Step 6: Verificar**

```bash
python -c "
import json
import pandas as pd
import config
from src.db_io import leer_tabla_sqlite

d = pd.read_csv(config.OUTPUTS_DIR / 'powerbi' / 'dimensionamiento.csv')
req = {'nivel','poblacion','desc_segmento','n_clientes',
       'monto_conservador','monto_base','monto_optimista',
       'monto_app_base','monto_prod_conservadores_base'}
assert req <= set(d.columns), req - set(d.columns)
assert set(d['nivel'].dropna()) <= {'A','B','C','D'}
assert set(d['poblacion']) == {'con_historial','sin_historial'}

fact = leer_tabla_sqlite(config.ORO_DB, 'fact_cliente_score')
assert d['n_clientes'].sum() == len(fact), 'el dimensionamiento no cubre toda la base'

with open(config.OUTPUTS_DIR / 'eda' / 'resumen_ejecutivo.json', encoding='utf-8') as f:
    r = json.load(f)
assert r['oportunidad_12m_conservador'] <= r['oportunidad_12m_base'] <= r['oportunidad_12m_optimista']
print(f'OK §7 — {r[\"n_clientes_total\"]:,} clientes, {r[\"n_nivel_A\"]:,} en nivel A')
print(f'   oportunidad 12m: [{r[\"oportunidad_12m_conservador\"]:,.0f} .. {r[\"oportunidad_12m_optimista\"]:,.0f}]')
"
```
Expected: `OK §7 — 860223 clientes, ... en nivel A` + el rango de oportunidad.

- [ ] **Step 7: Commit**

```bash
git add notebooks/05_dimensionamiento.ipynb
git commit -m "✨feat: add opportunity sizing notebook and executive summary (SPEC_V2 7)"
```

---

## Task 25 [MODIFICA]: `scripts/export_powerbi.py` — los 8 archivos de SPEC_V2 §8

**Files:**
- Modify: `scripts/export_powerbi.py`
- Create: `tests/test_export_powerbi.py`

**Interfaces:**
- Consumes: `oro.db` (`fact_cliente_score`, `dim_cliente`, `dim_producto`, `dim_tiempo`, `fact_saldos_mensual`), `outputs/eda/validacion_variables.csv` (Task 16), `outputs/models/importancia_permutacion.csv` (Task 18), `outputs/powerbi/fact_auditoria_sesgo.csv` (Task 22), `outputs/powerbi/dimensionamiento.csv` (Task 24).
- Produces: los 8 CSV de `outputs/powerbi/` y `outputs/powerbi/reporte_export.json` con el conteo de filas de cada uno.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_export_powerbi.py
import pandas as pd

from scripts.export_powerbi import construir_fact_importancia_variables


def test_fact_importancia_une_iv_e_importancia_de_permutacion():
    """SPEC_V2 §8: fact_importancia_variables = variable, importancia, IV, decisión."""
    validacion = pd.DataFrame({
        "variable": ["ingresos_mensuales", "ratio_pasivo_activo", "cdt_saldo_snapshot"],
        "iv": [0.45, 0.01, 0.22],
        "clase_iv": ["fuerte", "descartar", "media"],
        "decision_inclusion": ["incluir", "descartar_iv_insuficiente", "incluir"],
    })
    importancia = pd.DataFrame({
        "variable": ["ingresos_mensuales", "cdt_saldo_snapshot", "desc_segmento_PYME"],
        "importancia": [0.09, 0.04, 0.01],
        "modelo": ["A", "A", "A"],
    })
    r = construir_fact_importancia_variables(validacion, importancia)

    assert set(r.columns) >= {"variable", "importancia", "iv", "decision_inclusion", "modelo"}
    fila = r.set_index(["variable", "modelo"]).loc[("ingresos_mensuales", "A")]
    assert fila["iv"] == 0.45
    assert fila["importancia"] == 0.09
    # una variable con IV pero sin importancia (descartada) sigue apareciendo
    assert "ratio_pasivo_activo" in set(r["variable"])
    # una dummy sin IV propio también aparece, con IV nulo
    dummy = r[r["variable"] == "desc_segmento_PYME"]
    assert len(dummy) == 1
    assert pd.isna(dummy["iv"].iloc[0])
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
python -m pytest tests/test_export_powerbi.py -v
```
Expected: FAIL con `ImportError: cannot import name 'construir_fact_importancia_variables'`

- [ ] **Step 3: Reescribir `scripts/export_powerbi.py`**

```python
# scripts/export_powerbi.py
"""Export final para Power BI (SPEC_V2 §8).

Produce los 8 archivos de la tabla de §8. Los que generan los notebooks
(fact_auditoria_sesgo, dimensionamiento) no se regeneran aquí: se verifica su
presencia y se reporta su conteo de filas, para que el export sea la única
comprobación de que el entregable está completo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import config
from src.db_io import leer_tabla_sqlite

# Tablas que salen directamente de oro.db
TABLAS_ORO = {
    "fact_cliente_score": "fact_cliente_score",
    "dim_cliente": "dim_cliente",
    "dim_producto": "dim_producto",
    "dim_tiempo": "dim_tiempo",
    "fact_saldos_mensual": "fact_saldos_mensual",
}

# Archivos que producen los notebooks y aquí solo se verifican
GENERADOS_POR_NOTEBOOKS = ["fact_auditoria_sesgo.csv", "dimensionamiento.csv"]


def construir_fact_importancia_variables(validacion: pd.DataFrame,
                                         importancia: pd.DataFrame) -> pd.DataFrame:
    """SPEC_V2 §8: variable, importancia, IV, decisión de inclusión.

    Outer join: las variables descartadas por IV no aparecen en la importancia
    de permutación (no entraron al modelo) y las dummies generadas por
    get_dummies no tienen IV propio. Las dos situaciones deben quedar visibles
    en el entregable, no desaparecer por un inner join.
    """
    cols_val = [c for c in ["variable", "iv", "clase_iv", "vif", "q_bh",
                            "significativa_fdr", "decision_inclusion"]
                if c in validacion.columns]
    r = importancia.merge(validacion[cols_val], on="variable", how="outer")
    return r.sort_values(["modelo", "importancia"], ascending=[True, False],
                         na_position="last").reset_index(drop=True)


def main():
    destino = config.OUTPUTS_DIR / "powerbi"
    destino.mkdir(parents=True, exist_ok=True)
    reporte = {}

    for nombre, tabla in TABLAS_ORO.items():
        df = leer_tabla_sqlite(config.ORO_DB, tabla)
        ruta = destino / f"{nombre}.csv"
        df.to_csv(ruta, index=False)
        reporte[f"{nombre}.csv"] = len(df)
        print(f"{nombre}.csv: {len(df):,} filas")

    # fact_importancia_variables: IV (notebook 04) + permutation importance (notebook 02)
    ruta_val = config.OUTPUTS_DIR / "eda" / "validacion_variables.csv"
    ruta_imp = config.OUTPUTS_DIR / "models" / "importancia_permutacion.csv"
    if ruta_val.exists() and ruta_imp.exists():
        fiv = construir_fact_importancia_variables(
            pd.read_csv(ruta_val), pd.read_csv(ruta_imp))
        fiv.to_csv(destino / "fact_importancia_variables.csv", index=False)
        reporte["fact_importancia_variables.csv"] = len(fiv)
        print(f"fact_importancia_variables.csv: {len(fiv):,} filas")
    else:
        faltan = [str(p) for p in [ruta_val, ruta_imp] if not p.exists()]
        raise FileNotFoundError(
            f"faltan insumos de fact_importancia_variables: {faltan}. "
            "Ejecutar antes notebooks/04_validacion_variables.ipynb y 02_modelado.ipynb"
        )

    for nombre in GENERADOS_POR_NOTEBOOKS:
        ruta = destino / nombre
        if not ruta.exists():
            raise FileNotFoundError(
                f"{nombre} no existe. Lo produce un notebook: "
                "07_auditoria_sesgo.ipynb / 05_dimensionamiento.ipynb"
            )
        reporte[nombre] = len(pd.read_csv(ruta))
        print(f"{nombre}: {reporte[nombre]:,} filas (generado por notebook)")

    with open(destino / "reporte_export.json", "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    # SPEC_V2 §8: reportar el conteo de filas de fact_saldos_mensual tras la
    # agregación mensual, y comprobar que el volumen es razonable.
    n_mensual = reporte["fact_saldos_mensual.csv"]
    print(f"\nSPEC_V2 §8 — fact_saldos_mensual tras agregación mensual: {n_mensual:,} filas")
    assert n_mensual < 30_000_000, f"volumen desproporcionado: {n_mensual:,}"
    print(f"Export completo: {len(reporte)} archivos en {destino}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

```bash
python -m pytest tests/test_export_powerbi.py -v
```
Expected: `1 passed`

- [ ] **Step 5: Ejecutar el export real**

```bash
python scripts/export_powerbi.py
```
Expected: 8 líneas de conteo + `Export completo: 8 archivos en ...outputs/powerbi`

- [ ] **Step 6: Verificar los 8 archivos de §8**

```bash
python -c "
import json
import pandas as pd
import config
d = config.OUTPUTS_DIR / 'powerbi'
esperados = ['fact_cliente_score.csv','dim_cliente.csv','fact_auditoria_sesgo.csv',
             'fact_saldos_mensual.csv','dim_producto.csv','dim_tiempo.csv',
             'fact_importancia_variables.csv','dimensionamiento.csv']
faltan = [n for n in esperados if not (d / n).exists()]
assert not faltan, f'faltan: {faltan}'

s = pd.read_csv(d / 'fact_cliente_score.csv')
req = {'numero_id','score','nivel','monto_base_12m','monto_conservador_12m',
       'monto_optimista_12m','tiene_historial_inversion','modelo_usado',
       # D5: el export debe incluir los dos componentes ADEMÁS del total
       'monto_app_12m_base','monto_app_12m_conservador','monto_app_12m_optimista',
       'monto_prod_conservadores_12m_base','monto_prod_conservadores_12m_conservador',
       'monto_prod_conservadores_12m_optimista'}
assert req <= set(s.columns), req - set(s.columns)
assert s['numero_id'].is_unique
assert s['score'].notna().all()

c = pd.read_csv(d / 'dim_cliente.csv')
assert 'desc_genero' in c.columns   # SOLO para auditoría, nunca predictora

with open(d / 'reporte_export.json', encoding='utf-8') as f:
    r = json.load(f)
print('OK §8 — 8/8 archivos:')
for k, v in r.items():
    print(f'   {k}: {v:,} filas')
"
```
Expected: `OK §8 — 8/8 archivos:` seguido de los 8 conteos.

- [ ] **Step 7: Commit**

```bash
git add scripts/export_powerbi.py tests/test_export_powerbi.py
git commit -m "✨feat: export the 8 Power BI deliverables of SPEC_V2 8"
```

---

## Task 26 [MODIFICA]: orquestador y documentación

**Files:**
- Modify: `scripts/run_pipeline.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `python scripts/run_pipeline.py` ejecuta bronce → plata (incl. panel mensual) → oro → esquema estrella. Los notebooks quedan fuera (son interactivos) pero el README documenta el **orden obligatorio** de ejecución, que ahora sí tiene dependencias reales.

- [ ] **Step 1: Actualizar `_run_plata_transformacion` y el docstring**

```python
def _run_plata_transformacion():
    transformacion.limpiar_clientes()
    transformacion.transformar_aho_cte()
    for tabla_bronce, tabla_plata_destino in transformacion.FUENTES_PRODUCTO_UNICO:
        transformacion.transformar_producto_unico(tabla_bronce, tabla_plata_destino)
    transformacion.transformar_cdt_inversion_virtual()
    transformacion.transformar_estimador_ingresos()
    # SPEC_V2 §6.3.1 y §8: panel mensual con forward fill + primer registro
    transformacion.construir_saldos_mensual()
    transformacion.construir_primer_registro()
```

Reemplazar el docstring del módulo por:

```python
"""Orquestador del pipeline bronce -> plata -> oro (SPEC_V2).

Uso:
    python scripts/run_pipeline.py

Los notebooks NO se ejecutan aquí (son interactivos), pero a diferencia de la v1
ahora tienen dependencias reales entre sí. Orden obligatorio:

    1. python scripts/run_pipeline.py          (bronce, plata, oro, esquema estrella)
    2. notebooks/01_eda.ipynb
    3. notebooks/03_eda_faltantes.ipynb        -> decide el tratamiento de falta_estimador
    4. python -m oro.construir_cliente_features (aplica la decisión de perfil_incompleto)
    5. notebooks/04_validacion_variables.ipynb -> IV/WoE, decisión de vivienda
    6. notebooks/02_modelado.ipynb             -> modelos A y B, fact_cliente_score
    7. notebooks/06_monto_12m.ipynb            -> monto a 12m, actualiza fact_cliente_score
    8. notebooks/07_auditoria_sesgo.ipynb      -> fact_auditoria_sesgo.csv
    9. notebooks/05_dimensionamiento.ipynb     -> dimensionamiento.csv
   10. python scripts/export_powerbi.py        (falla si falta algún insumo)
"""
```

- [ ] **Step 2: Ejecutar el pipeline completo desde cero**

```bash
python scripts/run_pipeline.py
```
Expected: cada paso imprime `OK: <nombre>`. **`export_powerbi` fallará con `FileNotFoundError` si los notebooks no se han corrido** — es el comportamiento deseado, no un bug.

Nota: retirar `export_powerbi` del `main()` del orquestador y dejarlo como paso 10 manual, dado que ahora depende de artefactos de notebooks:

```python
def main():
    paso("bronce: extracción", extraccion.main)
    paso("bronce: diagnóstico de calidad", diagnostico_calidad.main)
    paso("plata: transformaciones", _run_plata_transformacion)
    paso("oro: cliente_features", construir_cliente_features.construir_cliente_features)
    paso("oro: esquema estrella", construir_esquema_estrella.construir_esquema_estrella)
    print(__doc__.split("Orden obligatorio:")[1])
    print("Pipeline de datos completo. Ejecutar los notebooks en el orden de arriba "
          "y después `python scripts/export_powerbi.py`.")
```

- [ ] **Step 3: Actualizar `README.md`**

Añadir una sección con: (a) el orden de ejecución de arriba, (b) la tabla de los 8 entregables de §8, (c) un enlace a este plan y a las Preguntas Abiertas, (d) la nota de que `desc_genero` está en `dim_cliente` solo para auditoría.

- [ ] **Step 4: Ejecutar toda la batería de tests**

```bash
python -m pytest tests/ -v
```
Expected: **todos verdes**. Recuento: `test_db_io` 2, `test_aggregations` 6, `test_fecha_corte` 2, `test_construir_cliente_features` 6, `test_fuga` 6, `test_features_modelo` 6, `test_panel_mensual` 8, `test_transformacion_mensual` 2, `test_derivadas` 15, `test_log_decisiones` 5, `test_granularidad` 14 (3 unitarios + 11 paramétricos contra datos reales), `test_decisiones` 23, `test_feature_tests` 24, `test_niveles` 6, `test_monto` 10, `test_auditoria_sesgo` 8, `test_esquema_estrella` 2, `test_export_powerbi` 1 → **146 passed**.

- [ ] **Step 5: Verificación final end-to-end**

```bash
python -c "
import json
import pandas as pd
import config
from src.db_io import leer_tabla_sqlite
from src.features_modelo import features_modelo_a, features_modelo_b
from src.fuga import validar_sin_fuga

cf = leer_tabla_sqlite(config.ORO_DB, 'cliente_features')
fs = leer_tabla_sqlite(config.ORO_DB, 'fact_cliente_score')

# §1 — sin fuga
validar_sin_fuga(features_modelo_a(cf.columns), contexto='verificacion final A')
validar_sin_fuga(features_modelo_b(cf.columns), contexto='verificacion final B')

# §1 — AUC bajo el umbral de sospecha
with open(config.OUTPUTS_DIR / 'models' / 'metricas_propension.json') as f:
    m = json.load(f)
for k in ['modelo_a','modelo_b']:
    assert m[k]['auc'] <= config.UMBRAL_AUC_FUGA

# §2 — toda la base scoreada
assert len(fs) == len(cf) == 860223
assert fs['score'].notna().all()
assert 'excluir_modelado' not in cf.columns

# §6.3 — monto NULL, no cero, para quien no tiene historial
assert fs.loc[fs['tiene_historial_inversion']==0, 'monto_base_12m'].isna().all()

# §10 — log de decisiones poblado
log = pd.read_csv(config.OUTPUTS_DIR / 'decisiones' / 'log_decisiones.csv')
assert len(log) >= 3, log

print('VERIFICACIÓN FINAL OK')
print(f'  §1 sin fuga | AUC A={m[\"modelo_a\"][\"auc\"]:.4f} B={m[\"modelo_b\"][\"auc\"]:.4f}')
print(f'  §2 {len(fs):,} clientes scoreados, 0 sin score')
print(f'  §10 {len(log)} decisiones registradas')
"
```
Expected: `VERIFICACIÓN FINAL OK` + las tres líneas de resumen.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_pipeline.py README.md
git commit -m "📄docs: update orchestrator and README with SPEC_V2 execution order"
```

---

## Trazabilidad SPEC_V2 → tareas

| Sección SPEC_V2 | Tareas | Tipo |
|---|---|---|
| §1 Fuga de información | 1, 2, 4, 5 | 1,4 nuevo · 2 modifica · 5 modifica |
| §1.3 test automático anti-fuga | **1** | nuevo (TDD) |
| §2 Población entrenamiento/scoring | 3, 5 | modifica |
| §3.1 Solapamiento | 13 | nuevo (notebook) |
| §3.2 Detección de patrón + tabla de decisión | **12** (lógica, TDD), 13 (aplicación) | nuevo |
| §3.3 Comparación de tasa de adopción | 13 | nuevo (notebook) |
| §3.4 No eliminar clientes | 13 (verificación explícita) | — |
| §4.1 IV/WoE | 15, 16 | nuevo |
| §4.2 Mann-Whitney | 15, 16 | nuevo |
| §4.3 Chi² + V de Cramér | 15, 16 | nuevo |
| §4.4 Benjamini-Hochberg | 15, 16 | nuevo |
| §4.5 VIF | 15, 16 | nuevo |
| §4.6 Permutation importance | 18 | modifica (notebook 02) |
| §5 Variables derivadas | 6, 7, 8, 9, 14 | 6,8 nuevo · 7,9,14 modifica |
| §6.1 Modelos A y B | 4, 18 | 4 nuevo · 18 modifica |
| §6.2 Niveles de prioridad | 17, 18, 20 | 17 nuevo · 18,20 notebook |
| §6.3 Modelo de monto 12m (**desbloqueada**) | 6, 19, 20 | nuevo |
| §6.4 Demográficas diferenciadas | 4, 16, 22 | nuevo |
| §6.5 Vivienda con "Sin dato" | 8, 12, 16 | nuevo |
| §6.6 Auditoría de sesgo | 21, 22 | nuevo |
| §7 Dimensionamiento | 24 | nuevo (notebook) |
| §8 Export Power BI | 23, 25 | modifica |
| §9 Granularidad | 11 | modifica |
| §10 Restricciones transversales | 0 (constraints), 10 (log), 26 (README) | mixto |

### Trazabilidad DECISIONES.md → tareas

| Decisión | Tareas | Efecto |
|---|---|---|
| D0 (recencia de la etiqueta, sensibilidad) | **2B** (nueva), **18B** (nueva) | `dias_desde_ultimo_dato`, `etiqueta_adopcion_reciente`, análisis de sensibilidad del Modelo A |
| D1 (definición de "ninguna señal") | 3 | confirma lo planificado |
| D2 (`sin_dato_financiero` any/all) | 3 | confirma lo planificado |
| D3 (`tendencia_relativa_6m`) | 8, 9, 16 | nueva variable por producto; compite con `tendencia_6m` en la validación de la Fase 4 |
| D4 (`FECHA_CORTE` global) | **0B** (nueva), 7, 9 | ventanas/snapshot/antigüedad contra una única referencia temporal |
| D5 (descomposición app/productos conservadores) | 20, 24, 25 | dos regresiones independientes + export con ambos componentes y el total |
| D6 (bandas de AUC del proxy de género) | 12, 22 | `decidir_interpretacion_proxy_genero` reemplaza al umbral único |
| D7 (lift condicional, no Jaccard) | 12, 13, 14 | `lift_condicional` reemplaza a `jaccard` en `perfil_incompleto` |
| D8 (antigüedad contra `FECHA_CORTE`) | 9 | ya no "mes máximo del panel" sino la fecha de corte explícita |
| D9 (`cv_saldo_liquido`) | 6, 7, 8, 9 | ventana fija 6M + mínimo 3 meses observados + coeficiente de variación |
| D10 (renombrar variable de diferencia de ingreso) | 4, 8 | `dif_ingreso_declarado_estimado` / `pct_dif_ingreso` |
| D11 (nombres de notebooks) | 20, 22 | confirma lo planificado |

## Resumen de tipo de tarea

**MODIFICAN código existente (14):** 0 (`config.py`, `requirements.txt`), 2, 3, 5, 7, 9, 11, 14, 18, 23, 25, 26 — más **0B** y **2B**, que modifican módulos creados en la misma Fase 1 (no en el plan v1, pero sí en tareas anteriores de este plan).

| Tarea | Archivo existente que toca |
|---|---|
| 0 | `config.py`, `requirements.txt` |
| 0B | `src/aggregations.py`, `plata/transformacion.py`, `tests/test_aggregations.py` |
| 2 | `oro/construir_cliente_features.py`, `tests/test_construir_cliente_features.py` |
| 2B | `oro/construir_cliente_features.py`, `tests/test_construir_cliente_features.py` |
| 3 | `oro/construir_cliente_features.py`, `plata/transformacion.py`, `bronce/diagnostico_calidad.py`, `tests/test_construir_cliente_features.py` |
| 5 | `notebooks/01_eda.ipynb`, `notebooks/02_modelado.ipynb` |
| 7 | `plata/transformacion.py` |
| 9 | `oro/construir_cliente_features.py` |
| 11 | `bronce/diagnostico_calidad.py` |
| 14 | `oro/construir_cliente_features.py` |
| 18 | `notebooks/02_modelado.ipynb` |
| 18B | `notebooks/02_modelado.ipynb` |
| 23 | `oro/construir_esquema_estrella.py` |
| 25 | `scripts/export_powerbi.py` |
| 26 | `scripts/run_pipeline.py`, `README.md` |

**CREAN código nuevo (16):** 1, 4, 6, 8, 10, 12, 13, 15, 16, 17, 19, 20, 21, 22, 24 — más **0B** (`src/fecha_corte.py`) — 10 módulos en `src/` con su test, y 5 notebooks nuevos (`03`, `04`, `05`, `06`, `07`).

**Con TDD estricto** (escribir el test, verlo fallar, implementar) — todo lo que toca `src/`, `plata/`, `oro/`: Tasks **0B, 1, 2, 2B, 3, 4, 6, 7, 8, 9, 10, 11, 12, 14, 15, 17, 19, 21, 23, 25** (20 tareas).

**Con verificación de salida** (ejecutar con `nbconvert` + comprobar el artefacto en `outputs/`), sin TDD — notebooks de EDA y modelado: Tasks **5, 13, 16, 18, 18B, 20, 22, 24** (8 tareas).

