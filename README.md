# Pipeline CREAN — Prueba Técnica

Pipeline de datos de arquitectura medallion (bronce / plata / oro) sobre SQLite,
con EDA y modelado en Jupyter, y export final para Power BI.

## Setup

Instalar dependencias en el venv del proyecto:

```
"C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" -m pip install -r requirements.txt
```

## Orden de ejecución

1. **Pasos automatizados** (extracción, calidad, transformaciones plata, features y
   esquema estrella oro, export Power BI) — un único punto de entrada:

   ```
   "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" scripts/run_pipeline.py
   ```

2. **Notebooks** (exploratorios/interactivos, se corren manualmente en Jupyter,
   no forman parte de `run_pipeline.py`):
   - `notebooks/01_eda.ipynb` — EDA y resumen de señal financiera. Recomendado
     correrlo primero porque documenta los datos antes de modelar, aunque ya
     **no es un prerequisito obligatorio** de `02_modelado.ipynb` (éste lee
     `cliente_features` directamente y filtra `excluir_modelado == 0`, sin
     depender del CSV que produce la EDA).
   - `notebooks/02_modelado.ipynb` — dataset de modelado, entrenamiento y
     evaluación del modelo de propensión de adopción.

3. **Export a Power BI** (también se ejecuta dentro de `run_pipeline.py`, se
   puede correr de forma independiente si solo se necesita refrescar el export):

   ```
   "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" scripts/export_powerbi.py
   ```

Los tests (`pytest tests/ -v` o `python -m pytest tests/ -v`) se pueden correr en
cualquier momento; no dependen de que el pipeline haya corrido (usan fixtures y
bases de datos temporales).

## Capas

- **bronce** (`bronce/`): extrae los `.db` de los `.zip` de origen y los carga
  tal cual a `bronce/data/bronce.db`, una tabla por fuente. `diagnostico_calidad.py`
  genera `outputs/quality/reporte_calidad.md` con nulos, duplicados, anomalías
  de encoding e integridad referencial — es diagnóstico, no transforma nada.
- **plata** (`plata/`): limpia clientes (dedup, `sin_dato_financiero`,
  `capacidad_ahorro`) y agrega las series de saldo por cliente/producto en
  ventanas de 6 meses (`saldo_snapshot`, `saldo_prom_6m`, `tendencia_6m`,
  `n_obs_ventana`, `tenencia`), escribiendo a `plata/data/plata.db`.
- **oro** (`oro/`): pivotea las tablas plata a nivel cliente
  (`cliente_features`, con `etiqueta_adopcion` y `excluir_modelado`) y arma un
  esquema estrella (`dim_cliente`, `dim_producto`, `dim_tiempo`, `fact_saldos`)
  en `oro/data/oro.db`, listo para BI.
- **outputs/**: artefactos generados — `quality/` (reporte de calidad),
  `eda/` (resúmenes y CSV de la EDA), `models/` (modelo entrenado, métricas,
  curva precisión/recall), `powerbi/` (CSV finales para Power BI).

## Decisiones de negocio provisionales

Varias reglas del pipeline (ventana de agregación, definición de
`etiqueta_adopcion`, etc.) son decisiones provisionales sujetas a confirmación
humana. La sección **"Preguntas Abiertas"** de
[`docs/superpowers/plans/2026-08-05-pipeline-crean.md`](docs/superpowers/plans/2026-08-05-pipeline-crean.md)
es la fuente de verdad sobre qué está pendiente de confirmar y por qué.

## Nota sobre `numero_id`

`numero_id` es un entero grande con signo, cercano a los límites de `int64`.
Herramientas que lo infieren como `float` (p. ej. Excel al abrir los CSV)
pierden precisión en los dígitos finales. La inferencia por defecto de
Power BI ("Whole Number") es correcta y no tiene este problema — verificar
que la importación no lo reinterprete como decimal.
