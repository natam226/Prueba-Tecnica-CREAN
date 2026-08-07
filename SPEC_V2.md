# SPEC v2 — Correcciones y ampliación del pipeline CREAN

Este documento reemplaza las decisiones abiertas de SPEC.md. El negocio dio
libertad total: no hay respuestas externas pendientes, todas las decisiones
están tomadas aquí y son definitivas salvo que el código demuestre que alguna
es inviable (en ese caso, documentar y preguntar, no improvisar).

La arquitectura medallón se mantiene sin cambios: bronce (ingesta cruda),
plata (transformaciones), oro (vista unificada).

---

## 1. CORRECCIÓN CRÍTICA — Fuga de información en el modelo de propensión

La etiqueta `adopcion` se define como saldo activo en Invesbot y/o Inversión
Virtual. Por lo tanto las siguientes variables NO pueden ser predictoras:

- `invesbot_saldo_snapshot`, `invesbot_saldo_prom_6m`, `invesbot_tendencia`
- `inv_virtual_saldo_snapshot`, `inv_virtual_saldo_prom_6m`, `inv_virtual_tendencia`
- `tiene_invesbot`, `tiene_inv_virtual`
- `n_productos_inversion` y `saldo_total_invertido` **tal como están definidas
  hoy**, porque suman los productos de la etiqueta
- `pct_patrimonio_invertido` si se calcula con esos saldos

Acciones:
1. Recalcular `n_productos_inversion_no_etiqueta` y
   `saldo_invertido_no_etiqueta` usando SOLO CDT y Fiducuenta.
2. Excluir explícitamente del conjunto de predictoras toda variable derivada
   de Invesbot o Inversión Virtual.
3. Añadir un test automático que falle si alguna variable con prefijo
   `invesbot_` o `inv_virtual_` entra al conjunto de entrenamiento.

Si el AUC del modelo supera 0.95, asumir que hay fuga residual e investigar
antes de continuar.

---

## 2. CORRECCIÓN — Población de scoring vs. población de entrenamiento

Estado actual: 90.548 clientes excluidos, de los cuales solo 81 tienen datos
financieros nulos. Los otros 90.467 tienen datos completos y fueron excluidos
solo por no tener historial de producto.

Comportamiento correcto:
- **Entrenamiento**: toda la base. Los clientes sin productos son ejemplos
  negativos legítimos y necesarios.
- **Scoring**: toda la base, sin excepción. Ningún cliente queda sin score.
- **Única exclusión admitida**: clientes sin ninguna señal en ninguna fuente
  (ni financiera ni de producto). Documentar cuántos son.

Reemplazar la bandera `excluir_modelado` por dos banderas separadas:
`apto_entrenamiento` y `tiene_historial_producto`.

---

## 3. NUEVO — EDA de valores faltantes en estimador de ingresos

Crear `notebooks/03_eda_faltantes.ipynb`.

### 3.1 Solapamiento
Calcular la intersección entre:
- clientes sin registro en `estimador_ingresos` (~114.431)
- clientes con nulos en las 5 columnas financieras (~260)

Reportar tamaño de la intersección y de cada conjunto por separado.

### 3.2 Detección de patrón (método principal)
Entrenar un clasificador auxiliar con variable objetivo `falta_estimador` (1/0)
y como predictoras el resto de variables disponibles (financieras, de producto,
demográficas). Reportar AUC y las 10 variables más importantes.

Interpretación y acción, a aplicar automáticamente según el resultado:

| AUC obtenido | Conclusión | Acción a implementar |
|---|---|---|
| < 0.60 | Ausencia aproximadamente aleatoria | Conservar bandera `falta_estimador`. No imputar si el modelo final maneja nulos nativamente; si no, imputar por mediana del `desc_segmento` |
| 0.60 – 0.70 | Patrón débil | Igual que el anterior, pero documentar las variables asociadas |
| > 0.70 | Ausencia informativa | Conservar la bandera como variable predictora de pleno derecho. NO imputar con medida central global. Imputar por mediana condicional al grupo identificado, o dejar nulo |

### 3.3 Comparación de tasa de adopción
Comparar el porcentaje de adoptadores entre el grupo con estimador y el grupo
sin estimador. Reportar la diferencia y su significancia (chi-cuadrado).

### 3.4 Restricción
NO eliminar clientes por falta de estimador de ingresos bajo ninguna
circunstancia. Son el 13,3% de la base y probablemente concentran el perfil de
adquisición en frío.

---

## 4. NUEVO — Validación estadística de variables

Crear `src/feature_tests.py` y `notebooks/04_validacion_variables.ipynb`.

Implementar y reportar en una tabla única por variable:

1. **IV / WoE (Information Value)** — estándar bancario para scorecards.
   Criterio: <0.02 descartar, 0.02–0.1 débil, 0.1–0.3 media, >0.3 fuerte.
   Reportar también el WoE por bin para las variables que se conserven.
2. **Mann-Whitney U** para continuas vs. etiqueta (no t-test: los datos
   financieros son fuertemente asimétricos).
3. **Chi-cuadrado + V de Cramér** para categóricas.
4. **Corrección Benjamini-Hochberg (FDR)** sobre todos los p-valores, porque
   se prueban decenas de variables simultáneamente.
5. **VIF** para multicolinealidad. Umbral de alerta: VIF > 10.
   Especial atención a patrimonio / activos / pasivos, relacionados por
   definición contable.
6. **Permutation importance** post-entrenamiento (más confiable que la
   importancia nativa de árboles).

La tabla resultante debe permitir justificar la inclusión o exclusión de cada
variable con un criterio explícito, no por intuición.

**Incluir en estas pruebas a `desc_genero`, `grupo_edad` y
`desc_tipo_de_vivienda`.** Las tres se miden. El resultado decide la inclusión
de edad y vivienda; para género se mide pero la exclusión está decidida por
criterio de idoneidad, no por su poder predictivo (ver sección 6.4).

Para `desc_tipo_de_vivienda`, calcular el IV tratando `"Sin dato"` como un bin
más, y calcular por separado el IV de la bandera binaria `tiene_dato_vivienda`
(ver sección 6.5).

---

## 5. NUEVO — Variables derivadas adicionales

Añadir a `cliente_features`, además de las ya existentes:

- `ratio_egreso_ingreso` = egresos / ingresos
- `pct_ahorro_ingreso` = capacidad de ahorro / ingresos
- `ratio_pasivo_activo` = pasivos / activos
- `patrimonio_por_ingreso` = patrimonio / (ingresos × 12)
- `gap_ingreso_estimado_declarado` = ingresos_mensuales − estimador_ingreso
- `pct_gap_ingreso` = gap / ingresos_mensuales
- `saldo_liquido_total` = saldo ahorros + corriente + bolsillos
- `ratio_liquidez_patrimonio` = saldo líquido / patrimonio
- `n_productos_total` = conteo de productos con saldo > 0 (todos)
- `n_productos_no_etiqueta` = conteo excluyendo Invesbot e Inv. Virtual
- `antiguedad_relacion_meses` = meses desde el primer registro en cualquier fuente
- `volatilidad_saldo_liquido` = desviación estándar del saldo líquido mensual
- `tiene_dato_vivienda` = bandera binaria (ver sección 6.5)
- `perfil_incompleto` = bandera única, solo si la verificación de la sección 6.5
  confirma solapamiento alto entre los distintos bloques de datos faltantes
- Banderas de dato faltante para cada bloque de variables

Todas las divisiones deben manejar denominador cero devolviendo nulo, no
infinito. Añadir tests para ese caso.

---

## 6. MODELOS — Diseño definitivo

### 6.1 Modelo de propensión — dos variantes

**Modelo A (completo)**
- Predictoras: capacidad financiera + comportamiento en productos que NO
  definen la etiqueta (CDT, Fiducuenta, Bolsillos, Ahorros, Corriente) +
  variables derivadas.
- Entrenamiento: toda la base apta.
- Aplicación: clientes con al menos un producto.

**Modelo B (cold-start / capacidad)**
- Predictoras: SOLO capacidad financiera y derivadas de ella (ingresos,
  egresos, capacidad de ahorro, patrimonio, activos, pasivos, estimador de
  ingreso, ratios). Ninguna variable de tenencia o saldo de producto.
- Entrenamiento: toda la base apta.
- Aplicación: clientes sin ningún producto (~90.467).

Reportar AUC de ambos por separado, y también el AUC de A restringido al
subconjunto que tiene productos.

**Restricción de interpretación a documentar en el notebook:** para el
segmento sin productos, la etiqueta es 0 por construcción (no puede haber
positivos). Por tanto el score de B sobre ese segmento es un puntaje de
similitud (lookalike), no una probabilidad validada. Reportarlo como ranking
relativo por niveles, nunca como porcentaje de probabilidad.

### 6.2 Niveles de prioridad

Asignar niveles A/B/C/D **por separado dentro de cada población**, para no
comparar poblaciones no comparables:

- Población con historial de inversión: ordenar por
  `valor_esperado = score × monto_estimado_12m`.
- Población sin historial: ordenar por score de similitud, con
  `capacidad_ahorro_anualizada` como referencia de valor (etiquetada
  explícitamente como proxy, no como pronóstico).

Usar cuartiles dentro de cada población. Documentar el criterio de corte.

### 6.3 Modelo de monto a 12 meses

Aplica **únicamente** a clientes con historial en productos de inversión
(Invesbot, Inversión Virtual, CDT o Fiducuenta con saldo > 0 en algún momento).

Pasos:
1. Construir panel mensual por cliente a partir de las series de saldo.
   Regularizar a frecuencia mensual con **forward fill** (un saldo persiste
   hasta el siguiente movimiento; NO interpolar linealmente).
2. Calcular el crecimiento observado del saldo invertido en la ventana
   disponible y anualizarlo.
3. Modelar el crecimiento a 12 meses con regresión, usando como predictoras el
   saldo actual, la tendencia histórica y las variables de capacidad financiera.
4. **Backtesting temporal obligatorio**: entrenar con los primeros N−3 meses,
   validar contra los últimos 3. Reportar MAE y MAPE.
5. Producir tres escenarios: conservador (percentil 25 del error), base
   (predicción central), optimista (percentil 75).

**Limitación a documentar explícitamente en el notebook:** con ~13 meses de
historia no es posible validar un horizonte de 12 meses de forma rigurosa ni
capturar estacionalidad anual. El resultado es una extrapolación validada
únicamente contra un horizonte de 3 meses. Reportar siempre como rango, nunca
como cifra única.

Los clientes sin historial reciben `monto_estimado_12m = NULL` y bandera
`tiene_historial_inversion = 0`. No imputar cero: no es cero, es desconocido.

### 6.4 Tratamiento diferenciado de variables demográficas

Estas tres variables NO reciben el mismo tratamiento. La decisión se toma por
criterio de idoneidad financiera, no por una regla general de precaución.

| Variable | ¿Entra al modelo? | Justificación |
|---|---|---|
| `desc_tipo_de_vivienda` | Sí (sujeto a sección 6.5) | No es atributo protegido. Propia / arrendada / familiar es indicador de estabilidad patrimonial |
| `grupo_edad` | Sí | En productos de inversión la edad determina horizonte de inversión y capacidad de asumir riesgo. Es criterio financiero estándar y esperado, no discriminación |
| `desc_genero` | **No** | No existe argumento de idoneidad financiera que justifique tratar distinto por sexo el acceso a un producto de inversión. Riesgo constitucional (art. 13) en entidad vigilada. Además, si resultara predictivo reflejaría desigualdad histórica de acceso, no propensión real |

Las tres se someten a las pruebas de la sección 4 (IV/WoE, chi-cuadrado,
V de Cramér). El resultado se usa para decidir inclusión en el caso de vivienda
y edad; en el caso de género se mide pero NO se usa como criterio de inclusión.

**Precaución específica para `grupo_edad`:** verificar que el modelo no excluya
sistemáticamente a los grupos de mayor edad. La adopción digital correlaciona
con edad, y existe el riesgo de estar prediciendo "usa aplicaciones" en vez de
"quiere invertir". Reportar tasa de selección al nivel A por grupo de edad.

### 6.5 Tipo de vivienda — alta proporción de nulos

`desc_tipo_de_vivienda` tiene aproximadamente 68% de valores nulos. NO imputar:
por encima del 50% de ausencia, la imputación fabrica la mayoría de la columna
y el modelo terminaría aprendiendo la imputación, no el comportamiento real.

Tratamiento correcto (*missing as a category*): convertir el nulo en un nivel
más de la variable categórica, con etiqueta `"Sin dato"`. No se inventa ningún
valor, se conserva la señal del 32% con dato, y si la ausencia es informativa el
modelo la captura sin decisión previa.

**Verificación previa obligatoria — riesgo de sesgo de captura:**
el dato de vivienda podría capturarse solo al tramitar crédito hipotecario o de
vivienda. Si es así, "tiene dato de vivienda" en realidad codifica vinculación
crediticia, no patrimonio. Comprobar:

1. Comparar patrimonio, ingresos y número de productos entre el grupo con dato
   y el grupo sin dato (Mann-Whitney).
2. Calcular el solapamiento con los clientes sin `estimador_ingreso`. Si es
   alto, existe una causa común de perfil incompleto: crear una sola bandera
   `perfil_incompleto` en vez de banderas separadas por variable.
3. Calcular la tasa de adopción por nivel, incluyendo `"Sin dato"` como uno más.

**Regla de decisión a aplicar automáticamente:**

| Resultado | Acción |
|---|---|
| IV total ≥ 0.02 (con `"Sin dato"` como bin) | Conservar la variable categórica con el nivel `"Sin dato"` |
| IV < 0.02 pero la bandera binaria `tiene_dato_vivienda` tiene IV propio ≥ 0.02 | Descartar la categórica, conservar solo la bandera |
| Ambos por debajo del umbral | Descartar por completo, dejando constancia de que se probó y no aportó |

### 6.6 Auditoría de sesgo

Independientemente de qué variables entren al modelo, ejecutar y reportar:

1. **Prueba de proxy para género.** Entrenar un clasificador que prediga
   `desc_genero` a partir del resto de variables predictoras. Si el AUC es alto,
   el género se filtra por variables correlacionadas y excluirlo de la lista de
   entrada no lo excluye del modelo. Reportar AUC y las variables más asociadas.
2. **Impacto dispar (regla del 80%).** Sobre la asignación final de niveles,
   calcular la tasa de selección al nivel A por cada grupo de género, edad y
   tipo de vivienda. Si la razón entre el grupo menos favorecido y el más
   favorecido cae por debajo de 0.8, reportarlo explícitamente como hallazgo.
3. **Diferencia de score promedio** entre grupos, con su significancia.

`desc_genero` se conserva en `dim_cliente` exclusivamente para esta auditoría y
para caracterización descriptiva del tablero. Nunca como predictora.

---

## 7. NUEVO — Dimensionamiento de la oportunidad

Crear `notebooks/05_dimensionamiento.ipynb` y exportar
`outputs/powerbi/dimensionamiento.csv`.

Producir:
- Número de clientes por nivel de prioridad, desagregado por población
  (con historial / sin historial)
- Monto potencial agregado por nivel, en los tres escenarios, solo para la
  población con historial
- Distribución de niveles por `desc_segmento`
- Tabla resumen ejecutiva: total de clientes priorizados y rango de oportunidad

---

## 8. Export para Power BI

`scripts/export_powerbi.py` debe producir:

| Archivo | Contenido |
|---|---|
| `fact_cliente_score.csv` | numero_id, score, nivel, monto_estimado_12m (nullable), escenarios, tiene_historial_inversion, modelo_usado (A o B) |
| `dim_cliente.csv` | Atributos descriptivos. Incluye `desc_genero` SOLO para auditoría y caracterización, nunca como predictora |
| `fact_auditoria_sesgo.csv` | Tasas de selección por grupo, razón de impacto dispar, resultado de la prueba de proxy |
| `fact_saldos_mensual.csv` | cliente, producto, mes, saldo — **agregado a nivel mensual**, no diario |
| `dim_producto.csv`, `dim_tiempo.csv` | Catálogos |
| `fact_importancia_variables.csv` | Variable, importancia, IV, decisión de inclusión |
| `dimensionamiento.csv` | Resumen por nivel y segmento |

Verificar que `fact_saldos_mensual` tenga un volumen razonable tras la
agregación mensual y reportar el conteo de filas.

---

## 9. Verificaciones de granularidad (añadir al diagnóstico)

1. Confirmar unicidad de la combinación (numero_id, producto, fecha) en cada
   tabla de producto en bronce.
2. Confirmar que `numero_id` es único en `cliente_features` y que el conteo
   coincide con el de clientes deduplicados.
3. Confirmar que ninguna tabla de plata aporta más de una fila por
   cliente-producto.

---

## 10. Restricciones transversales

- No eliminar clientes salvo la única exclusión definida en la sección 2.
- Toda decisión de imputación debe quedar registrada en un log de decisiones.
- Todo modelo debe reportar sus métricas en el notebook, no solo pasar un test.
- Mantener el enfoque TDD para la lógica de transformación en `src/`, `plata/`
  y `oro/`. Para los notebooks de EDA y modelado, priorizar verificaciones de
  salida sobre TDD estricto.