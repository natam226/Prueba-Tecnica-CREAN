# Pipeline CREAN — Prueba Técnica

Pipeline de datos de arquitectura medallion (bronce / plata / oro) sobre SQLite,
con EDA, modelado, auditoría de sesgo y dimensionamiento de oportunidad en
Jupyter, y export final para Power BI. Implementa SPEC_V2
(`docs/superpowers/plans/2026-08-06-pipeline-crean-v2.md`), que corrige y
amplía el plan v1 original.

## Setup

Instalar dependencias en el venv del proyecto:

```
"C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" -m pip install -r requirements.txt
```

## Orden de ejecución (SPEC_V2 — obligatorio, no solo recomendado)

A diferencia de la v1, los notebooks de SPEC_V2 tienen dependencias reales
entre sí (uno lee un artefacto que produce el anterior), así que el orden
importa:

1. **Pasos automatizados** — bronce, plata (incl. panel mensual de saldos),
   oro (`cliente_features` + esquema estrella). Un único punto de entrada:

   ```
   "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" scripts/run_pipeline.py
   ```

2. `notebooks/01_eda.ipynb` — EDA y resumen de señal financiera.
3. `notebooks/03_eda_faltantes.ipynb` — decide el tratamiento de
   `falta_estimador` y mide el `lift_condicional` (D7) entre bloques de datos
   faltantes; escribe `outputs/eda/faltantes_solapamiento.json`.
4. **Reconstruir `cliente_features`** — este paso vuelve a ejecutar
   `oro/construir_cliente_features.py`, que ahora sí lee el JSON del paso 3
   para decidir si crea la bandera `perfil_incompleto`. Si se salta este paso
   (o se corre antes que el 3), `cliente_features` queda con la decisión sin
   aplicar:

   ```
   "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" -m oro.construir_cliente_features
   ```

5. `notebooks/04_validacion_variables.ipynb` — batería IV/WoE, Mann-Whitney,
   Cramér V, BH-FDR y VIF; decide el tratamiento de `desc_tipo_de_vivienda`.
6. `notebooks/02_modelado.ipynb` — entrena los modelos de propensión A y B,
   escora toda la base y crea `fact_cliente_score` en `oro.db`.
7. `notebooks/06_monto_12m.ipynb` — modelo de monto potencial a 12 meses
   (descompuesto en componente "app" y "productos conservadores", D5);
   **actualiza** `fact_cliente_score` con las columnas de monto y recalcula
   `nivel` para la población con historial.
8. `notebooks/07_auditoria_sesgo.ipynb` — auditoría de sesgo (proxy de
   género, regla del 80%, brecha de score); produce
   `outputs/powerbi/fact_auditoria_sesgo.csv`.
9. `notebooks/05_dimensionamiento.ipynb` — dimensionamiento de oportunidad por
   nivel/población/segmento; produce `outputs/powerbi/dimensionamiento.csv` y
   `outputs/eda/resumen_ejecutivo.json`.
10. **Export final a Power BI** — falla explícitamente con `FileNotFoundError`
    si falta cualquier insumo de los pasos 3-9 (a propósito: no genera un
    export parcial en silencio):

    ```
    "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" scripts/export_powerbi.py
    ```

Los tests (`pytest tests/ -v` o `python -m pytest tests/ -v`) se pueden correr en
cualquier momento; no dependen de que el pipeline haya corrido (usan fixtures y
bases de datos temporales).

## Estado de verificación (léase antes de confiar en cualquier cifra)

El código de los pasos 6-10 (modelado, monto a 12 meses, auditoría de sesgo,
dimensionamiento, export) fue escrito e integrado contra los módulos y esquemas
reales del repositorio, pero **los notebooks 05 y 07 no se han ejecutado**
todavía de punta a punta en esta rama — quedan como entregable listo para
correr, no como resultado verificado. Las cifras de `fact_auditoria_sesgo.csv`,
`dimensionamiento.csv` y `resumen_ejecutivo.json` no existen hasta que alguien
los ejecute. Los pasos 1-7 (bronce/plata/oro, EDA, modelado de propensión,
monto a 12 meses) sí se han corrido sobre datos reales al menos una vez; las
cifras de la sección siguiente vienen de esas corridas.

## Resultados actuales (medidos, con su contexto — no citar sin él)

- **Modelo de propensión a adopción**: AUC Modelo A = **0.8942**, Modelo B
  (cold-start, solo capacidad financiera) = **0.8375**, sobre 860,223 clientes
  escoreados (0 sin score). Esta es la cifra **posterior** a corregir una fuga
  de etiqueta: `dias_desde_ultimo_dato`, `sin_dato_reciente` y
  `antiguedad_relacion_meses` se calculaban originalmente sobre las 7 fuentes
  de producto SIN excluir Invesbot/Inversión Virtual (los productos que
  definen la etiqueta), lo que inflaba el AUC a 0.9320 y luego a 0.9497 según
  qué versión del feature set se usara — ambas por encima, o peligrosamente
  cerca, del umbral de sospecha de fuga (`UMBRAL_AUC_FUGA = 0.95`). Al
  redefinir esas tres variables sobre las 5 fuentes no-etiqueta el AUC bajó a
  0.8942, estadísticamente idéntico a simplemente eliminarlas (0.8941) — la
  evidencia de que el cierre de la fuga es real y no un side-effect distinto.
  Ver `outputs/decisiones/log_decisiones.csv` (clave `fuga_recencia_antiguedad`)
  para la investigación completa.
- **Modelo de monto potencial a 12 meses**: corregido por sesgo. El modelo
  sobre-predecía sistemáticamente (backtest de 3 meses con error negativo en
  ~92% de los clientes del componente "app" y ~77% del componente
  "productos conservadores"), así que el escenario `base` ya NO es la
  predicción cruda: se recentra en `predicción + mediana(error de backtest)`
  por componente, y el rango `[conservador, optimista]` usa los percentiles
  10/90 del error (no 25/75, que colapsaba a ancho cero para el componente
  "app"). Ver `DECISIONES.md`, clave `metrica_error_monto`.
- **El agregado `[conservador, optimista]` de la oportunidad a 12 meses NO es
  una banda de incertidumbre agregada válida** (hallazgo encontrado durante
  esta tarea, sin resolver): se construye sumando el límite p10/p90 de cada
  cliente por separado (~220 mil clientes con historial de inversión), lo que
  asume que todos caen simultáneamente en su propio peor (o mejor) caso. Bajo
  independencia razonable la incertidumbre agregada debería escalar con
  `sqrt(n)`, no con `n` — el rango mostrado está sobrestimado en órdenes de
  magnitud, y el límite "conservador" agregado puede incluso salir negativo
  sin que eso signifique que el modelo esté roto. `notebooks/05_dimensionamiento.ipynb`
  mide esta discrepancia con evidencia real (no simulada), la imprime junto a
  la cifra, y registra una decisión en el log (`agregacion_rango_oportunidad_12m`)
  dejando claro que **solo la cifra `base` es defendible como titular** frente
  al negocio mientras no se decida un método de agregación correcto. Esto es
  una decisión de negocio pendiente, no resuelta en este notebook a propósito.

## Entregables de Power BI (SPEC_V2 §8)

`scripts/export_powerbi.py` produce estos 8 archivos en `outputs/powerbi/` (los
dos últimos los generan los notebooks 07 y 05; el export solo los verifica y
reporta su conteo de filas):

| Archivo | Origen | Contenido |
|---|---|---|
| `fact_cliente_score.csv` | `oro.db` | score, nivel, monto 12m (total + componentes app/productos conservadores), población |
| `dim_cliente.csv` | `oro.db` | `grupo_edad`, `desc_genero`, `desc_segmento`, `desc_tipo_de_vivienda` por cliente |
| `dim_producto.csv` | `oro.db` | catálogo de productos |
| `dim_tiempo.csv` | `oro.db` | dimensión de tiempo a grano **mensual** |
| `fact_saldos_mensual.csv` | `oro.db` | serie de saldo mensual cliente-producto |
| `fact_importancia_variables.csv` | `outputs/eda` + `outputs/models` | IV/WoE (notebook 04) + importancia de permutación (notebook 02), unidas por variable |
| `fact_auditoria_sesgo.csv` | notebook 07 | regla del 80%, brecha de score, AUC del proxy de género, por atributo/grupo |
| `dimensionamiento.csv` | notebook 05 | monto agregado por nivel/población/segmento, descompuesto en app + productos conservadores |

## Capas

- **bronce** (`bronce/`): extrae los `.db` de los `.zip` de origen y los carga
  tal cual a `bronce/data/bronce.db`, una tabla por fuente. `diagnostico_calidad.py`
  genera `outputs/quality/reporte_calidad.md` con nulos, duplicados, anomalías
  de encoding e integridad referencial — es diagnóstico, no transforma nada.
- **plata** (`plata/`): limpia clientes (dedup, `sin_dato_financiero`,
  `capacidad_ahorro`) y agrega las series de saldo por cliente/producto en
  ventanas de 6 meses (`saldo_snapshot`, `saldo_prom_6m`, `tendencia_6m`,
  `n_obs_ventana`, `tenencia`) y en un panel mensual con forward-fill
  (`saldos_mensual_plata`, base de `fact_saldos_mensual` y del modelo de monto
  a 12 meses), escribiendo a `plata/data/plata.db`.
- **oro** (`oro/`): pivotea las tablas plata a nivel cliente
  (`cliente_features`, con `etiqueta_adopcion`) y arma un esquema estrella
  (`dim_cliente`, `dim_producto`, `dim_tiempo` mensual, `fact_saldos` snapshot,
  `fact_saldos_mensual`) en `oro/data/oro.db`, listo para BI. `dim_cliente`
  incluye `desc_genero` — se conserva **exclusivamente** para la auditoría de
  sesgo (`notebooks/07_auditoria_sesgo.ipynb`) y para caracterización
  descriptiva del tablero; la exclusión de `desc_genero` como predictora del
  modelo de propensión es un criterio de **idoneidad**, no de poder
  predictivo (SPEC_V2 §6.4) — si resultara predictivo reflejaría una
  desigualdad histórica de acceso, no una señal que el modelo deba aprender a
  usar. Verificado en código por `src/features_modelo.py` y en test por
  `tests/test_features_modelo.py`.
- **outputs/**: artefactos generados — `quality/` (reporte de calidad),
  `eda/` (resúmenes y CSV de la EDA), `models/` (modelos entrenados, métricas,
  curva precisión/recall), `decisiones/` (log de decisiones, ver abajo),
  `powerbi/` (los 8 CSV finales para Power BI).

## `outputs/` está en `.gitignore` — pendiente de decidir

Todo `outputs/` (incluido `outputs/decisiones/log_decisiones.csv`, el log de
decisiones que SPEC_V2 §10 exige como entregable) está excluido del control de
versiones. Eso significa que, tal como está configurado hoy, **el log de
decisiones no queda versionado junto con el código que lo generó** — cada
corrida local lo regenera (es append-only, así que además crece sin límite si
se corre el pipeline varias veces sin limpiarlo). Esto no se ha resuelto en
esta tarea porque es una decisión del usuario, no técnica. Opciones a elegir:

1. Sacar `outputs/decisiones/` (o directamente `log_decisiones.csv`) de
   `.gitignore` y versionarlo como cualquier otro entregable de auditoría.
2. Exportarlo también a un destino no ignorado (p. ej. dentro de
   `outputs/powerbi/` si ese directorio se versiona, o a un lugar fuera de
   `outputs/`).
3. Dejarlo como está y documentar explícitamente que el log de decisiones es
   un artefacto de ejecución, no un entregable versionado — y decidir cómo se
   entrega entonces (adjunto aparte, capturado en el reporte final, etc.).

## Decisiones de negocio

Las reglas de negocio del pipeline (ventana de agregación, definición de
`etiqueta_adopcion`, bandas de interpretación del proxy de género, tratamiento
de `perfil_incompleto`, etc.) están documentadas como código testeable en
`src/decisiones.py` y registradas, corrida a corrida, en
`outputs/decisiones/log_decisiones.csv` (ver la sección de arriba sobre por
qué ese archivo no está versionado). El razonamiento narrativo detrás de cada
decisión — incluida la corrección de la fuga de etiqueta y la corrección de
sesgo del modelo de monto — vive en `DECISIONES.md`. Ese archivo (junto con
`SPEC_V2.md`) vive en la raíz del repositorio principal y, al momento de
escribir esto, no está presente como archivo trackeado dentro de este
worktree (`worktree-pipeline-crean-sdd`) ni de `.superpowers/sdd/` — si no lo
encuentras aquí, búscalo en el checkout principal. El plan de implementación
sí está versionado en este worktree:
[`docs/superpowers/plans/2026-08-06-pipeline-crean-v2.md`](docs/superpowers/plans/2026-08-06-pipeline-crean-v2.md).
La sección **"Preguntas Abiertas"** del plan v1
([`docs/superpowers/plans/2026-08-05-pipeline-crean.md`](docs/superpowers/plans/2026-08-05-pipeline-crean.md))
sigue siendo la referencia de qué quedaba pendiente de confirmar antes de
SPEC_V2; varias de esas preguntas ya fueron resueltas por las decisiones D0-D10
que SPEC_V2 aplica (ver la cabecera de `DECISIONES.md`).

## Nota sobre `numero_id`

`numero_id` es un entero grande con signo, cercano a los límites de `int64`.
Herramientas que lo infieren como `float` (p. ej. Excel al abrir los CSV)
pierden precisión en los dígitos finales. La inferencia por defecto de
Power BI ("Whole Number") es correcta y no tiene este problema — verificar
que la importación no lo reinterprete como decimal.
