# Spec — Pipeline analítico App de Inversiones CREAN

## Objetivo
Construir un pipeline reproducible que integre 7 fuentes SQLite (entregadas en .zip)
en una arquitectura medallón (bronce-plata-oro), genere una tabla `cliente_features`
a nivel cliente, entrene un modelo de propensión a adopción y un modelo de monto
potencial a 12 meses, y deje los resultados listos para consumir desde Power BI.

## Fuentes de datos (bronce)
Cada fuente viene en un .zip independiente con una base SQLite (.db), una sola tabla:
- clientes.db → tabla clientes (860.231 filas, 1 fila/cliente)
  columnas: numero_id, grupo_edad, desc_genero, desc_segmento,
  desc_tipo_de_vivienda, ingresos_mensuales, total_egresos_mensuales,
  total_activos, total_pasivos, total_patrimonio
- ahorros_corriente.db → columnas: fecha, numero_id, producto, saldo
  producto ∈ {CUENTA DE AHORRO, CUENTA DE CORRIENTE}
- bolsillos.db → mismas columnas, producto = BOLSILLOS
- fiducuenta.db → mismas columnas, producto = FIDUCUENTA
- cdt_inversion_virtual.db → mismas columnas,
  producto ∈ {CDT, INVERSIÓN VIRTUAL}
- invesbot.db → mismas columnas, producto = INVESBOT
- estimador_ingresos.db → columnas: numero_id, producto, estimador_ingreso
  (sin fecha), producto = ESTIMADOR INGRESO

## Supuestos de negocio (ya definidos, no reabrir sin avisar)
- Etiqueta "adopción" = saldo activo en Invesbot y/o Inversión Virtual
- CDT y Fiducuenta son señal/predictor, no parte de la etiqueta
- Capacidad de ahorro = ingresos_mensuales − total_egresos_mensuales
- Cliente sin registro en una tabla de producto = saldo 0 / tenencia No
- Clientes nulos en las 5 columnas financieras: conservar si tienen actividad
  en alguna tabla de producto (bandera sin_dato_financiero); excluir del
  modelado solo si no tienen ninguna señal en ninguna fuente
- Variables sensibles (género, edad, tipo de vivienda) → solo caracterización
  descriptiva, nunca como input del modelo de propensión

## Arquitectura esperada
- bronce/: ingesta cruda de los 7 .db, sin transformar
- plata/: una tabla por fuente, agregada a nivel cliente (o cliente-producto
  cuando el producto se desagrega), con snapshot (último saldo), promedio 6M
  y tendencia para las series de tiempo
- oro/: 
  - cliente_features (ancha, 1 fila por cliente) → para modelado
  - esquema estrella liviano (fact_saldos + dim_cliente/producto/tiempo) →
    para el tablero

## Stack
- Python (pandas / PySpark), sqlite3 para lectura de los .db
- Docker opcional para reproducibilidad del entorno
- Salida final consumible desde Power BI

## Entregables
1. Script/notebook de extracción bronce (lee los .zip, extrae los .db, carga a bronce)
2. Script de transformación plata (agregaciones y desagregación por producto)
3. Script de construcción de cliente_features (oro)
4. Notebook de EDA
5. Notebook de modelado (propensión + monto)
6. Export de resultados para Power BI