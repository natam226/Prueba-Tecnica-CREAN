# Pipeline CREAN — Prueba Técnica

Pipeline de datos de arquitectura medallion (bronce / plata / oro) sobre SQLite,
con EDA, modelado, auditoría de sesgo y dimensionamiento de oportunidad en
Jupyter, una interfaz de resultados en Streamlit y export final para Power BI.
Implementa `SPEC_V2.md` con las decisiones de `DECISIONES.md`.

## Documentos

| Documento | Contenido |
|---|---|
| [`docs/diccionario_datos.md`](docs/diccionario_datos.md) | Las 90 columnas de `cliente_features` y las restricciones del esquema estrella. **Generado**, no escrito a mano |
| [`docs/modelo_conceptual.md`](docs/modelo_conceptual.md) | Modelo conceptual, diagrama de procesos con actores y puntos de decisión, y aporte a los procesos de CREAN |
| [`docs/esquema_operacion.md`](docs/esquema_operacion.md) | Cómo se generan, actualizan y consumen los resultados; seguimiento, mantenimiento y evolución |
| [`cloudflare/README.md`](cloudflare/README.md) | Publicación web sobre Workers + D1, y el despliegue automático desde GitHub Actions |
| `DECISIONES.md` | Razonamiento narrativo detrás de cada decisión analítica |
| `SPEC_V2.md` | Especificación que implementa el pipeline |

## Dónde corre cada cosa

| | Dónde | Qué lo publica |
|---|---|---|
| Pipeline, modelos y notebooks | local | — |
| Tablero del analista (Streamlit) | local, `streamlit run app/tablero.py` | — |
| Vitrina web pública | Cloudflare Workers | `.github/workflows/ci.yml`, en cada push a `main` |
| Datos de la vitrina | Cloudflare D1 | carga local y manual, **no** el workflow |

La última fila es la que se olvida: publicar código no actualiza los datos. Si
se vuelve a correr el pipeline hay que regenerar el volcado y recargar D1 a
mano, o la web seguirá mostrando la corrida anterior.

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

11. **Diccionario de datos** — regenera `docs/diccionario_datos.md` desde la
    base real: las 90 columnas de `cliente_features` con su papel en los
    modelos, y las restricciones del esquema estrella.

    ```
    "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" scripts/diccionario_datos.py
    ```

12. **Interfaz de resultados** — lee los artefactos de `outputs/`, no recalcula
    nada. Corre en local, sin desplegar:

    ```
    "C:\Users\natam\OneDrive\Desktop\Prueba-Tecnica-CREAN\venv\Scripts\python.exe" -m streamlit run app/tablero.py
    ```

Los tests (`pytest tests/ -v` o `python -m pytest tests/ -v`) se pueden correr en
cualquier momento; no dependen de que el pipeline haya corrido (usan fixtures y
bases de datos temporales).

## Estado de verificación (léase antes de confiar en cualquier cifra)

Los 12 pasos se han ejecutado de punta a punta sobre los datos reales, y las
cifras de la sección siguiente vienen de esas corridas. El export produce los 8
archivos y falla explícitamente si falta cualquier insumo, así que un export
completo es en sí mismo la comprobación de que la cadena corrió entera.

Los notebooks se versionan **con sus salidas**: son parte del entregable, no
solo el código que las produce.

## Resultados actuales (medidos, con su contexto — no citar sin él)

- **Modelo de propensión a adopción**: AUC Modelo A = **0.8933**, Modelo B
  (cold-start, solo capacidad financiera) = **0.8338**, sobre 860,223 clientes
  escoreados (0 sin score). Esta es la cifra **posterior** a corregir una fuga
  de etiqueta: `dias_desde_ultimo_dato`, `sin_dato_reciente` y
  `antiguedad_relacion_meses` se calculaban originalmente sobre las 7 fuentes
  de producto SIN excluir Invesbot/Inversión Virtual (los productos que
  definen la etiqueta), lo que inflaba el AUC a 0.9320 y luego a 0.9497 según
  qué versión del feature set se usara — ambas por encima, o peligrosamente
  cerca, del umbral de sospecha de fuga (`UMBRAL_AUC_FUGA = 0.95`). Al
  redefinir esas tres variables sobre las 5 fuentes no-etiqueta el AUC bajó a
  0.8933, estadísticamente idéntico a simplemente eliminarlas (0.8931) — la
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
- **Bruto vs neto**: el modelo proyecta el *cambio neto* del saldo invertido,
  mientras que el brief pide "el monto potencial que podrían invertir", que es
  un flujo de entrada. Se reportan por separado: **entrada bruta 1,859,309 M
  COP** (179,405 clientes, la cifra que responde al brief), **salida bruta
  −760,259 M COP** (40,137 clientes, que es una base de retención accionable y
  nominada, no un error de signo) y **neto 1,099,051 M COP**. Reportar solo el
  neto subestima la captación al restarle un problema de negocio distinto.
- **Los niveles B y C no diferencian monto**: la dispersión del monto dentro de
  cada uno es exactamente cero — un único valor distinto (17.46 COP) en 42,572
  y 4,465 clientes respectivamente. El árbol colapsa a una constante en la zona
  media y el recentrado por mediana la cancela. Siguen siendo cuartiles válidos
  para **priorizar contacto** (van sobre el score, que sí discrimina), pero no
  aportan resolución para **dimensionar**, así que `05_dimensionamiento.ipynb`
  los agrupa en un `bloque_comercial` derivado de la dispersión medida, no de
  una lista fija.
- **El rango agregado NO se deriva del error del modelo.** Sumar el p10/p90 de
  cada uno de los ~220 mil clientes asume que todos caen a la vez en su propio
  peor (o mejor) caso: da una banda de ancho 498% de la base, con el extremo
  inferior en negativo. Pero el extremo opuesto tampoco sirve — bajo
  independencia la banda escala con `sqrt(n)`≈469 en vez de `n` y se reduce a
  un ancho de 1.1%, precisión que una proyección a 12 meses sobre ~13 meses de
  historia no puede tener. La correlación real de los errores entre clientes no
  es estimable con una sola ventana temporal, así que **ninguno de los dos
  extremos es defendible**. Ese callejón sin salida es el hallazgo: la
  incertidumbre que manda no es el error del modelo sino la **adopción**. Por
  eso el rango se construye sobre una palanca de negocio explícita,
  `oportunidad = entrada_bruta × tasa_de_captura` con la tasa en
  `config.TASAS_CAPTURA` (10% / 25% / 40% → 185,931 / 464,827 / 743,724 M COP).
  Los escenarios **por cliente** se conservan y siguen siendo válidos para
  ordenar; lo que se descarta es su suma. Ver la clave
  `agregacion_rango_oportunidad_12m` en el log de decisiones.

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
- **El esquema de oro está declarado** en `oro/esquema.py`: llaves primarias,
  NOT NULL, tres llaves foráneas dentro del esquema estrella e índices sobre
  las columnas que las consultas usan de verdad. `pandas.to_sql` crea tablas
  sin ninguna restricción, así que durante buena parte del proyecto la
  integridad se sostuvo solo en las pruebas; ahora la base la hace cumplir.
  Las foráneas se verifican con `PRAGMA foreign_keys = ON` al escribir el
  estrella, que por eso se escribe entero y en orden de dependencia.
- **oro** (`oro/`): pivotea las tablas plata a nivel cliente
  (`cliente_features`, con `etiqueta_adopcion`) y arma un esquema estrella
  (`dim_cliente`, `dim_producto`, `dim_tiempo` mensual y `fact_saldos_mensual`) en `oro/data/oro.db`, listo para BI. `dim_cliente`
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
- **app** (`app/`): tablero de resultados en Streamlit, separado en tres
  archivos — `tablero.py` (las vistas), `estilo.py` (paleta, CSS y formateo de
  cifras) y `datos.py` (carga cacheada). El tema vive en
  `.streamlit/config.toml`. Solo lee `outputs/`; si una cifra no cuadra con un
  notebook, el notebook manda. No carga `fact_saldos_mensual` (9.9 M filas): la
  serie mensual se agrega en el pipeline, no en la capa de presentación.

  El contenido vive en `app/paginas/`, un módulo por vista. Siete vistas en el
  orden en que se sustenta, cada una declarando la pregunta que responde:

  | Vista | Responde | Requerimiento del brief |
  |---|---|---|
  | Resumen | Qué se hizo y para qué | — |
  | Los clientes | Qué distingue a quien invierte | 2 · analizar y caracterizar |
  | La solución | Qué se construyó y qué tan bien funciona | 3 · uno o más modelos |
  | La oportunidad | Cuánto dinero puede entrar | 4 · dimensionar la oportunidad |
  | A quién contactar | Cuántas llamadas y a quiénes | 7 · recomendaciones accionables |
  | Supuestos y sesgos | Qué asumimos y qué encontramos | — |
  | Cómo opera | Datos, procesos CREAN y mantenimiento | 1 · modelo de datos · 5 · procesos · 6 · operación |

  **Convención de tono, porque el público de la sustentación es mixto:** cada
  sección abre con la respuesta en lenguaje llano (`estilo.respuesta`) y guarda
  el sustento técnico en un cajón plegado (`estilo.detalle`). Quien viene del
  negocio lee la superficie; quien viene de lo técnico abre el cajón. Una
  prueba automática verifica que ninguna vista pierda su bloque de respuesta.

  La vista *A quién contactar* incluye la **curva de esfuerzo**: contactando al
  10% mejor rankeado se alcanza al 51.2% de los adoptantes con 36.7% de
  precisión, 5.1× la tasa base. Es la tabla que convierte el AUC en una
  decisión operativa. Y la **ficha de cliente** responde «¿y este por qué?» con
  la evidencia de WoE que lo distingue.

  Los diagramas de *Cómo opera* se dibujan con `st.graphviz_chart` a partir de
  cadenas DOT — Streamlit los renderiza de forma nativa, sin dependencias
  nuevas.

  `numero_id` se carga como **texto** en el tablero y la exportación sale en
  UTF-8 con BOM: el identificador es un entero de 19 dígitos (hasta ±9.2e18) y
  cualquier herramienta que lo infiera como decimal le cambia los últimos
  dígitos en silencio.

## Qué se versiona de `outputs/`

Se versiona la **evidencia**, no los datos regenerables. Quien revise el
repositorio necesita ver qué se decidió y con qué respaldo estadístico; no
necesita 9.9 millones de filas de saldos mensuales que puede reconstruir
corriendo el pipeline.

| Se versiona | Por qué |
|---|---|
| `decisiones/log_decisiones.csv` | trazabilidad de supuestos, exigida por SPEC_V2 §10 |
| `eda/validacion_variables.csv` | la validación estadística de las 64 variables |
| `eda/*.json`, `eda/*.png` | resúmenes y patrones de faltantes |
| `models/*.json`, `models/importancia_permutacion.csv` | métricas y AUC |

Quedan fuera `outputs/powerbi/` (cientos de MB) y `outputs/models/*.pkl`
(binarios). El log es *append-only*: crece con cada corrida, así que conviene
limpiarlo antes de una entrega si se corrió el pipeline varias veces.

## Decisiones de negocio

Las reglas de negocio del pipeline (ventana de agregación, definición de
`etiqueta_adopcion`, bandas de interpretación del proxy de género, tratamiento
de `perfil_incompleto`, etc.) están documentadas como código testeable en
`src/decisiones.py` y registradas, corrida a corrida, en
`outputs/decisiones/log_decisiones.csv`. El razonamiento narrativo detrás de
cada decisión — incluida la corrección de la fuga de etiqueta y la corrección
de sesgo del modelo de monto — vive en `DECISIONES.md`, junto a `SPEC_V2.md`
en la raíz del repositorio.

## Nota sobre `numero_id`

`numero_id` es un entero grande con signo, cercano a los límites de `int64`.
Herramientas que lo infieren como `float` (p. ej. Excel al abrir los CSV)
pierden precisión en los dígitos finales. La inferencia por defecto de
Power BI ("Whole Number") es correcta y no tiene este problema — verificar
que la importación no lo reinterprete como decimal.
