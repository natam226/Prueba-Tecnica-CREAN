# DECISIONES — Resolución de preguntas abiertas

Este documento resuelve las preguntas marcadas como PROVISIONAL en la especificación.
Tiene precedencia sobre las decisiones provisionales del plan. Donde una decisión
aquí contradiga SPEC.md o SPEC_V2.md, vale esta.

---

## D0. Recencia de la etiqueta de adopción

**Decisión: se mantiene la definición actual** — etiqueta positiva si el último
saldo observado en Invesbot y/o Inversión Virtual es mayor que cero, sin exigir
recencia.

**Razón:** un snapshot antiguo con saldo positivo no evidencia que el cliente
haya abandonado el producto; evidencia que no hay dato reciente. Exigir recencia
clasificaría como negativo a un cliente del que simplemente no tenemos
información actualizada, introduciendo un sesgo contra clientes cuyas fuentes se
actualizan con menor frecuencia.

**Requisitos adicionales obligatorios:**

1. Añadir la variable `dias_desde_ultimo_dato` por cliente (respecto a
   `FECHA_CORTE`, ver D4) como control de calidad de dato.
2. Ejecutar un **análisis de sensibilidad**: reentrenar el modelo de propensión
   con una etiqueta alternativa que exija saldo positivo dentro de los últimos
   90 días, y comparar contra el modelo principal:
   - AUC de ambos
   - Correlación de Spearman entre los dos rankings de clientes
   - Porcentaje de clientes que cambian de nivel de prioridad
3. Documentar el resultado en el notebook de modelado. Si el ranking se mantiene
   estable, declararlo como evidencia de que la decisión no es determinante. Si
   cambia sustancialmente, reportar ambos escenarios.

---

## D1. Definición de "ninguna señal en ninguna fuente"

**Decisión: aprobada la propuesta provisional.**

Un cliente se excluye únicamente si cumple las tres condiciones a la vez:
- (a) no tiene fila en ninguna de las 5 tablas de producto, Y
- (b) no tiene fila en `estimador_ing`, Y
- (c) tiene nulas las 5 columnas financieras

`estimador_ing` SÍ cuenta como señal: su existencia implica que hubo suficiente
actividad transaccional para estimar un ingreso, lo cual es información sobre el
cliente.

Reportar el conteo exacto de clientes excluidos bajo esta regla.

---

## D2. `sin_dato_financiero`: any vs. all

**Decisión: aprobada la propuesta provisional.** Se conservan ambas variables:

- `sin_dato_financiero` (`.any()`, ~260 clientes) — bandera descriptiva, puede
  entrar como predictora si el IV lo justifica.
- `sin_dato_financiero_total` (`.all()`, ~249 clientes) — usada por la regla de
  exclusión de D1(c).

---

## D3. Definición de tendencia

**Decisión: se conserva la definición actual** (media de la segunda mitad de la
ventana menos media de la primera mitad), por ser robusta a valores atípicos y
fácil de explicar a audiencia de negocio.

**Adición obligatoria:** crear también `tendencia_relativa`:

```
tendencia_relativa = tendencia / saldo_prom_6m
```

**Razón:** la tendencia en pesos absolutos no es comparable entre clientes de
distinta escala patrimonial. Un incremento de un millón significa algo muy
distinto para un cliente con cien millones que para uno con un millón.

Ambas variables pasan por las pruebas de la sección 4 de SPEC_V2. Se conserva la
que obtenga mejor IV; si ambas superan el umbral y no son colineales (VIF < 10),
se conservan las dos.

Manejar denominador cero devolviendo nulo.

---

## D4. Fecha de corte y ventana de 6 meses

**Decisión: se CAMBIA la propuesta provisional. Se usa una fecha de corte
global, no una por fuente.**

```
FECHA_CORTE = min(max_fecha de cada una de las 5 fuentes de saldo)
            = 2026-06-01 (verificar en datos)
```

Todas las ventanas de 6 meses, el snapshot de último saldo y la antigüedad se
calculan contra esta única referencia.

**Razón:** con cortes por fuente, cada cliente queda medido en un momento
distinto y los saldos dejan de ser estrictamente comparables entre clientes. El
costo es descartar hasta 29 días de las fuentes más recientes; el beneficio es
que toda la base queda medida contra la misma referencia temporal, que es más
defendible y más simple de explicar.

Registrar en el log de decisiones cuántos registros quedan fuera por fuente al
aplicar el corte global.

---

## D5. Saldo invertido objetivo del modelo de monto

**Decisión: aprobada la propuesta provisional (los 4 productos), con requisito
de descomposición.**

El objetivo a proyectar es el saldo invertido total sumando Invesbot, Inversión
Virtual, CDT y Fiducuenta.

**Requisito obligatorio:** el resultado debe reportarse **descompuesto en dos
componentes**:

1. Saldo en productos de tipo aplicación (Invesbot + Inversión Virtual) —
   comportamiento autogestionado, el más análogo a la nueva App.
2. Saldo en productos conservadores (CDT + Fiducuenta) — recursos que podrían
   migrar hacia la App bajo un supuesto de migración que debe declararse.

**Razón:** el enunciado pide estimar el volumen de recursos que podrían
canalizarse a través del nuevo servicio. Parte de ese volumen sería crecimiento
en comportamiento tipo App, y parte sería migración de saldos existentes. Son
cifras distintas con implicaciones distintas para el negocio, y reportarlas por
separado evita depender de una interpretación única del enunciado.

El export a Power BI debe incluir ambas columnas además del total.

---

## D6. Umbral de AUC en la prueba de proxy de género

**Decisión: se reemplaza el umbral único por bandas de interpretación.**

| AUC del clasificador de género | Interpretación | Acción |
|---|---|---|
| < 0.60 | Proxy mínimo | Documentar y continuar |
| 0.60 – 0.70 | Proxy moderado | Documentar las variables más asociadas al género y reportarlo como limitación |
| > 0.70 | Proxy sustancial | Investigar qué variables lo generan y evaluar mitigación antes de considerar el modelo definitivo |

**Razón:** un umbral binario oculta el caso intermedio, que es el resultado más
probable y el que más requiere documentación explícita.

---

## D7. Umbral de solapamiento para `perfil_incompleto`

**Decisión: se CAMBIA la propuesta provisional. El índice de Jaccard no es
aplicable en este caso.**

Los conjuntos tienen tamaños muy desbalanceados: sin `estimador_ingreso` son
~114.431 clientes; sin `desc_tipo_de_vivienda` son ~585.000 (68% de la base).
Aun con contención perfecta del conjunto menor en el mayor, el Jaccard máximo
posible sería ~0,195. El umbral de 0,50 es inalcanzable por construcción y la
regla nunca se activaría.

**Medida correcta: lift condicional.**

```
P(sin vivienda | sin estimador) / P(sin vivienda | con estimador)
```

- Lift ≥ 1.5 → hay causa común de incompletitud. Crear la bandera única
  `perfil_incompleto` y usarla en lugar de banderas separadas.
- Lift < 1.5 → las ausencias son independientes. Conservar banderas separadas
  por bloque de variables.

Reportar el valor del lift obtenido, no solo la decisión resultante.

---

## D8. Fecha de referencia de `antiguedad_relacion_meses`

**Decisión: aprobada, usando `FECHA_CORTE` global de D4** en vez del
`MAX(fecha)` por fuente.

```
antiguedad_relacion_meses = meses entre FECHA_CORTE y el primer registro
                            del cliente en cualquier fuente
```

---

## D9. Ventana de `volatilidad_saldo_liquido`

**Decisión: aprobada con tres ajustes.**

1. **Ventana fija de 6 meses** contada desde `FECHA_CORTE`, no todo el historial
   disponible. Clientes con historias de distinta longitud producen desviaciones
   no comparables entre sí.
2. **Mínimo de 3 meses con dato**; por debajo de eso, devolver nulo con bandera,
   no un valor calculado sobre muy pocos puntos.
3. Usar **coeficiente de variación** (desviación estándar / media) en vez de la
   desviación absoluta, por la misma razón de escala de D3. Nombrar la variable
   `cv_saldo_liquido`. Manejar media cero devolviendo nulo.

---

## D10. Nombre de la variable de diferencia de ingreso

**Decisión: se conserva la fórmula del spec y se renombra la variable.**

```
dif_ingreso_declarado_estimado = ingresos_mensuales − estimador_ingreso
```

También renombrar la variable porcentual correspondiente a
`pct_dif_ingreso`.

**Razón:** un nombre que contradice su propia fórmula es una fuente garantizada
de error de interpretación más adelante, tanto en el código como en la
sustentación.

---

## D11. Nombres de notebooks

**Decisión: aprobada la propuesta provisional.**

- `notebooks/06_monto_12m.ipynb`
- `notebooks/07_auditoria_sesgo.ipynb`

---

## Regla general para futuras ambigüedades

Cuando una decisión no esté cubierta por SPEC.md, SPEC_V2.md o este documento:

1. Elegir la opción que preserve más información y descarte menos clientes.
2. Preferir la opción más fácil de explicar a audiencia de negocio sobre la
   técnicamente más sofisticada, si el beneficio es marginal.
3. Ante dos opciones defendibles, implementar la principal y añadir un análisis
   de sensibilidad que compare ambas, como en D0.
4. Registrar la decisión y su justificación en el log de decisiones.
