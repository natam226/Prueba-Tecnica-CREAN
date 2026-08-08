# Diccionario de datos — capa oro

**Generado por `scripts/diccionario_datos.py` desde la base real.** No
editar a mano: se regenera y se pierde. Para cambiar una descripción,
editar el diccionario `DESCRIPCIONES` de ese script.

`cliente_features`: **860,223 filas × 90 columnas**, una fila por cliente.

## Esquema estrella

| Tabla | Filas | Llave primaria | Restricciones |
|---|---|---|---|
| `dim_cliente` | 860,223 | `numero_id` | — |
| `dim_producto` | 7 | `producto_id` | UNIQUE |
| `dim_tiempo` | 13 | `fecha_id` | UNIQUE |
| `fact_saldos_mensual` | 9,869,655 | `numero_id, producto_id, mes` | 3 llaves foráneas, 2 índices |
| `fact_cliente_score` | 860,223 | `numero_id` | 1 índice |

Las restricciones se declaran en `oro/esquema.py` y las aplica
`escribir_tabla_sqlite`. Las foráneas se verifican con
`PRAGMA foreign_keys = ON` al escribir el estrella.

## Columnas de `cliente_features`

La columna **papel** dice qué hace cada variable en los modelos. «FUGA» marca las que derivan de los productos que definen la etiqueta: un guard automático falla si alguna llega al entrenamiento.

| Columna | Tipo | Nulos | Papel | IV | Decisión | Descripción |
|---|---|---|---|---|---|---|
| `numero_id` | int64 | 0 | identificador o bandera |  |  | Identificador del cliente. Entero de hasta 19 dígitos: excede el entero exacto de coma flotante, así que fuera de SQLite viaja como texto. |
| `grupo_edad` | str | 0 | predictora · modelos A y B | 0.127 | incluir | Rango etario. Entra al modelo. |
| `desc_genero` | str | 93 (0.0%) | excluida por idoneidad | 0.039 | excluida_por_idoneidad_no_por_poder_predictivo | Género. Se conserva SOLO para auditoría de sesgo; nunca entra al modelo. |
| `desc_segmento` | str | 0 | predictora · modelos A y B | 0.852 | incluir | Segmento comercial. Es la variable con más poder predictivo de la base. |
| `desc_tipo_de_vivienda` | str | 0 | predictora · modelos A y B | 0.121 | incluir | Tipo de vivienda. Mide, en parte, profundidad de la relación con el banco. |
| `ingresos_mensuales` | float64 | 249 (0.0%) | predictora · modelos A y B | 1.182 | incluir_con_alerta_multicolinealidad | Ingreso mensual declarado. Viene de la fuente de clientes. |
| `total_egresos_mensuales` | float64 | 249 (0.0%) | predictora · modelos A y B | 0.126 | incluir_con_alerta_multicolinealidad | Egreso mensual declarado. |
| `total_activos` | float64 | 249 (0.0%) | predictora · modelos A y B | 1.027 | incluir | Activos declarados. |
| `total_pasivos` | float64 | 249 (0.0%) | predictora · modelos A y B | 0.172 | incluir | Pasivos declarados. |
| `total_patrimonio` | float64 | 260 (0.0%) | predictora · modelos A y B | 0.734 | incluir | Patrimonio declarado. |
| `sin_dato_financiero` | int64 | 0 | predictora · modelos A y B | 0.001 | descartar_iv_insuficiente | 1 si faltan las cinco columnas financieras. |
| `sin_dato_financiero_total` | int64 | 0 | predictora · modelo A | 0.001 | descartar_iv_insuficiente | Variante que exige que falten todas. |
| `capacidad_ahorro` | float64 | 249 (0.0%) | predictora · modelos A y B | 0.998 | incluir_con_alerta_multicolinealidad | ingresos_mensuales − total_egresos_mensuales. Excedente mensual disponible para invertir. |
| `cuenta_ahorro_saldo_snapshot` | float64 | 0 | predictora · modelo A | 1.485 | incluir_con_alerta_multicolinealidad | Último saldo observado en cuenta de ahorro. |
| `cuenta_ahorro_fecha_snapshot` | str | 386,941 (45.0%) | artefacto intermedio |  |  | Fecha del último registro de cuenta de ahorro. Artefacto intermedio, no predictora. |
| `cuenta_ahorro_saldo_prom_6m` | float64 | 90,495 (10.5%) | predictora · modelo A | 1.407 | incluir | Saldo promedio de cuenta de ahorro en la ventana de 6 meses. |
| `cuenta_ahorro_tendencia_6m` | float64 | 446,113 (51.9%) | predictora · modelo A | 0.808 | incluir | Pendiente del saldo de cuenta de ahorro en 6 meses (crecimiento absoluto). |
| `cuenta_ahorro_n_obs_ventana` | int64 | 0 | predictora · modelo A | 0.486 | incluir | Meses con dato observado de cuenta de ahorro dentro de la ventana. |
| `cuenta_ahorro_tenencia` | int64 | 0 | predictora · modelo A | 0.938 | incluir | 1 si el cliente tiene cuenta de ahorro. |
| `cuenta_corriente_saldo_snapshot` | float64 | 0 | predictora · modelo A | 0.034 | incluir_con_alerta_multicolinealidad | Último saldo observado en cuenta corriente. |
| `cuenta_corriente_fecha_snapshot` | str | 854,578 (99.3%) | artefacto intermedio |  |  | Fecha del último registro de cuenta corriente. Artefacto intermedio, no predictora. |
| `cuenta_corriente_saldo_prom_6m` | float64 | 1,449 (0.2%) | predictora · modelo A | 0.034 | incluir_con_alerta_multicolinealidad | Saldo promedio de cuenta corriente en la ventana de 6 meses. |
| `cuenta_corriente_tendencia_6m` | float64 | 4,528 (0.5%) | predictora · modelo A | 0.031 | incluir_con_alerta_multicolinealidad | Pendiente del saldo de cuenta corriente en 6 meses (crecimiento absoluto). |
| `cuenta_corriente_n_obs_ventana` | int64 | 0 | predictora · modelo A | 0.027 | incluir | Meses con dato observado de cuenta corriente dentro de la ventana. |
| `cuenta_corriente_tenencia` | int64 | 0 | predictora · modelo A | 0.036 | incluir | 1 si el cliente tiene cuenta corriente. |
| `bolsillos_saldo_snapshot` | float64 | 0 | predictora · modelo A | 0.611 | incluir_con_alerta_multicolinealidad | Último saldo observado en bolsillos. |
| `bolsillos_fecha_snapshot` | str | 599,509 (69.7%) | artefacto intermedio |  |  | Fecha del último registro de bolsillos. Artefacto intermedio, no predictora. |
| `bolsillos_saldo_prom_6m` | float64 | 10,064 (1.2%) | predictora · modelo A | 0.662 | incluir_con_alerta_multicolinealidad | Saldo promedio de bolsillos en la ventana de 6 meses. |
| `bolsillos_tendencia_6m` | float64 | 121,922 (14.2%) | predictora · modelo A | 0.576 | incluir | Pendiente del saldo de bolsillos en 6 meses (crecimiento absoluto). |
| `bolsillos_n_obs_ventana` | int64 | 0 | predictora · modelo A | 1.075 | incluir | Meses con dato observado de bolsillos dentro de la ventana. |
| `bolsillos_tenencia` | int64 | 0 | predictora · modelo A | 1.171 | incluir | 1 si el cliente tiene bolsillos. |
| `fiducuenta_saldo_snapshot` | float64 | 0 | predictora · modelo A | 1.243 | incluir_con_alerta_multicolinealidad | Último saldo observado en Fiducuenta. |
| `fiducuenta_fecha_snapshot` | str | 679,369 (79.0%) | artefacto intermedio |  |  | Fecha del último registro de Fiducuenta. Artefacto intermedio, no predictora. |
| `fiducuenta_saldo_prom_6m` | float64 | 3,431 (0.4%) | predictora · modelo A | 1.285 | incluir_con_alerta_multicolinealidad | Saldo promedio de Fiducuenta en la ventana de 6 meses. |
| `fiducuenta_tendencia_6m` | float64 | 43,494 (5.1%) | predictora · modelo A | 0.790 | incluir | Pendiente del saldo de Fiducuenta en 6 meses (crecimiento absoluto). |
| `fiducuenta_n_obs_ventana` | int64 | 0 | predictora · modelo A | 1.228 | incluir | Meses con dato observado de Fiducuenta dentro de la ventana. |
| `fiducuenta_tenencia` | int64 | 0 | predictora · modelo A | 1.294 | incluir | 1 si el cliente tiene Fiducuenta. |
| `cdt_saldo_snapshot` | float64 | 0 | predictora · modelo A | 0.035 | incluir_con_alerta_multicolinealidad | Último saldo observado en CDT. |
| `cdt_fecha_snapshot` | str | 834,249 (97.0%) | artefacto intermedio |  |  | Fecha del último registro de CDT. Artefacto intermedio, no predictora. |
| `cdt_saldo_prom_6m` | float64 | 1,610 (0.2%) | predictora · modelo A | 0.045 | incluir_con_alerta_multicolinealidad | Saldo promedio de CDT en la ventana de 6 meses. |
| `cdt_tendencia_6m` | float64 | 3,923 (0.5%) | predictora · modelo A | 0.041 | incluir | Pendiente del saldo de CDT en 6 meses (crecimiento absoluto). |
| `cdt_n_obs_ventana` | int64 | 0 | predictora · modelo A | 0.029 | incluir | Meses con dato observado de CDT dentro de la ventana. |
| `cdt_tenencia` | int64 | 0 | predictora · modelo A | 0.016 | descartar_iv_insuficiente | 1 si el cliente tiene CDT. |
| `inversion_virtual_saldo_snapshot` | float64 | 0 | FUGA · nunca predictora |  |  | Último saldo observado en Inversión Virtual. |
| `inversion_virtual_fecha_snapshot` | str | 800,455 (93.1%) | FUGA · nunca predictora |  |  | Fecha del último registro de Inversión Virtual. Artefacto intermedio, no predictora. |
| `inversion_virtual_saldo_prom_6m` | float64 | 8,983 (1.0%) | FUGA · nunca predictora |  |  | Saldo promedio de Inversión Virtual en la ventana de 6 meses. |
| `inversion_virtual_tendencia_6m` | float64 | 22,551 (2.6%) | FUGA · nunca predictora |  |  | Pendiente del saldo de Inversión Virtual en 6 meses (crecimiento absoluto). |
| `inversion_virtual_n_obs_ventana` | int64 | 0 | FUGA · nunca predictora |  |  | Meses con dato observado de Inversión Virtual dentro de la ventana. |
| `inversion_virtual_tenencia` | int64 | 0 | FUGA · nunca predictora |  |  | 1 si el cliente tiene Inversión Virtual. |
| `invesbot_saldo_snapshot` | float64 | 0 | FUGA · nunca predictora |  |  | Último saldo observado en Invesbot. |
| `invesbot_fecha_snapshot` | str | 855,179 (99.4%) | FUGA · nunca predictora |  |  | Fecha del último registro de Invesbot. Artefacto intermedio, no predictora. |
| `invesbot_saldo_prom_6m` | float64 | 196 (0.0%) | FUGA · nunca predictora |  |  | Saldo promedio de Invesbot en la ventana de 6 meses. |
| `invesbot_tendencia_6m` | float64 | 1,263 (0.1%) | FUGA · nunca predictora |  |  | Pendiente del saldo de Invesbot en 6 meses (crecimiento absoluto). |
| `invesbot_n_obs_ventana` | int64 | 0 | FUGA · nunca predictora |  |  | Meses con dato observado de Invesbot dentro de la ventana. |
| `invesbot_tenencia` | int64 | 0 | FUGA · nunca predictora |  |  | 1 si el cliente tiene Invesbot. |
| `estimador_ingreso` | float64 | 114,431 (13.3%) | predictora · modelos A y B | 1.264 | incluir_con_alerta_multicolinealidad | Ingreso estimado a partir de patrones transaccionales. Su ausencia es informativa: señala una relación transaccional delgada con el banco. |
| `tiene_estimador_ingreso` | int64 | 0 | predictora · modelos A y B | 0.405 | incluir | Complemento de falta_estimador. |
| `etiqueta_adopcion` | int64 | 0 | FUGA · nunca predictora |  |  | 1 si el cliente tiene saldo activo en Invesbot o Inversión Virtual. Es la variable objetivo. |
| `dias_desde_ultimo_dato` | float64 | 332,063 (38.6%) | predictora · modelo A | 1.587 | incluir | Días desde el último registro en alguna fuente que NO define la etiqueta. |
| `sin_dato_reciente` | int64 | 0 | predictora · modelo A | 1.375 | incluir | 1 si no hay ningún registro reciente en fuentes que no definen la etiqueta. |
| `etiqueta_adopcion_reciente` | int64 | 0 | FUGA · nunca predictora |  |  | Etiqueta alternativa que además exige actividad en los últimos 90 días. Solo se usa en el análisis de sensibilidad. |
| `saldo_invertido_no_etiqueta` | float64 | 0 | predictora · modelo A | 1.019 | incluir_con_alerta_multicolinealidad | Saldo en CDT y Fiducuenta. |
| `n_productos_inversion_no_etiqueta` | int64 | 0 | predictora · modelo A | 1.247 | incluir | Número de productos de inversión que no definen la etiqueta: CDT y Fiducuenta. |
| `tiene_historial_producto` | int64 | 0 | identificador o bandera |  |  | 1 si el cliente tiene al menos un producto. Define qué modelo se le aplica. |
| `sin_ninguna_senal` | int64 | 0 | identificador o bandera |  |  | 1 si el cliente no aparece en ninguna fuente de producto ni financiera. |
| `apto_entrenamiento` | int64 | 0 | identificador o bandera |  |  | 1 si el cliente tiene alguna señal en alguna fuente. Excluye a quien no aparece en ninguna. |
| `ratio_egreso_ingreso` | float64 | 9,545 (1.1%) | predictora · modelos A y B | 0.144 | incluir_con_alerta_multicolinealidad | egresos / ingresos. Presión de gasto, normalizada por nivel de ingreso. |
| `pct_ahorro_ingreso` | float64 | 9,545 (1.1%) | predictora · modelos A y B | 0.145 | incluir_con_alerta_multicolinealidad | capacidad_ahorro / ingresos. Tasa de ahorro, comparable entre escalas. |
| `ratio_pasivo_activo` | float64 | 97,349 (11.3%) | predictora · modelos A y B | 0.267 | incluir | pasivos / activos. Apalancamiento. |
| `patrimonio_por_ingreso` | float64 | 9,554 (1.1%) | predictora · modelos A y B | 0.494 | incluir | patrimonio / ingresos. Riqueza acumulada relativa al flujo. |
| `dif_ingreso_declarado_estimado` | float64 | 114,607 (13.3%) | predictora · modelos A y B | 0.512 | incluir_con_alerta_multicolinealidad | Diferencia entre el ingreso declarado y el estimado. |
| `pct_dif_ingreso` | float64 | 116,876 (13.6%) | predictora · modelos A y B | 0.639 | incluir | Esa diferencia normalizada por el ingreso declarado. |
| `saldo_liquido_total` | float64 | 0 | predictora · modelo A | 1.838 | incluir_con_alerta_multicolinealidad | Suma de ahorro, corriente y bolsillos. |
| `n_productos_total` | int64 | 0 | FUGA · nunca predictora |  |  | Número de productos del cliente, incluidos los que definen la etiqueta. NO es predictora. |
| `n_productos_no_etiqueta` | int64 | 0 | predictora · modelo A | 2.150 | incluir | Número de productos excluyendo Invesbot e Inversión Virtual. |
| `ratio_liquidez_patrimonio` | float64 | 164,591 (19.1%) | predictora · modelo A | 1.442 | incluir | saldo_liquido_total / patrimonio. |
| `cuenta_ahorro_tendencia_relativa_6m` | float64 | 833,869 (96.9%) | predictora · modelo A | 0.020 | descartar_iv_insuficiente | Tendencia de cuenta de ahorro dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `cuenta_corriente_tendencia_relativa_6m` | float64 | 859,280 (99.9%) | predictora · modelo A | 0.008 | descartar_iv_insuficiente | Tendencia de cuenta corriente dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `bolsillos_tendencia_relativa_6m` | float64 | 770,096 (89.5%) | predictora · modelo A | 0.438 | incluir | Tendencia de bolsillos dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `fiducuenta_tendencia_relativa_6m` | float64 | 722,863 (84.0%) | predictora · modelo A | 0.812 | incluir | Tendencia de Fiducuenta dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `cdt_tendencia_relativa_6m` | float64 | 838,172 (97.4%) | predictora · modelo A | 0.002 | descartar_iv_insuficiente | Tendencia de CDT dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `inversion_virtual_tendencia_relativa_6m` | float64 | 823,006 (95.7%) | FUGA · nunca predictora |  |  | Tendencia de Inversión Virtual dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `invesbot_tendencia_relativa_6m` | float64 | 856,442 (99.6%) | FUGA · nunca predictora |  |  | Tendencia de Invesbot dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala. |
| `tiene_dato_vivienda` | int64 | 0 | predictora · modelos A y B | 0.108 | descartar | Complemento de falta_vivienda. |
| `falta_financiero` | int64 | 0 | predictora · modelo A | 0.001 | descartar_iv_insuficiente | 1 si falta alguna de las columnas financieras. |
| `falta_estimador` | int64 | 0 | predictora · modelos A y B | 0.405 | incluir | 1 si el cliente no tiene estimador de ingresos. Es el predictor negativo más fuerte de la base. |
| `falta_vivienda` | int64 | 0 | predictora · modelo A | 0.108 | descartar | 1 si no hay dato de tipo de vivienda. Afecta al 69% de la base. |
| `cv_saldo_liquido` | float64 | 728,362 (84.7%) | predictora · modelo A | 0.409 | incluir | Coeficiente de variación del saldo líquido en la ventana de 6 meses. Se usa el coeficiente y no la desviación para que sea comparable entre escalas. |
| `cv_saldo_liquido_insuficiente` | int64 | 0 | predictora · modelo A | 0.375 | incluir | 1 si hay menos de 3 meses realmente observados para calcular el coeficiente. Un saldo arrastrado por relleno tiene volatilidad artificial cero. |
| `antiguedad_relacion_meses` | float64 | 331,037 (38.5%) | predictora · modelo A | 1.616 | incluir | Meses entre la fecha de corte y el primer registro del cliente en alguna fuente que NO define la etiqueta. |
