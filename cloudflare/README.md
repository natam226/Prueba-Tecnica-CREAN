# Tablero público en Cloudflare

Versión web de los resultados, servida desde Cloudflare Workers con la base de
datos en D1. Es una **capa de publicación**, no un reemplazo del pipeline.

## Qué corre aquí y qué no

| | Dónde vive | Por qué |
|---|---|---|
| Pipeline (bronce/plata/oro) | **Local** | Workers dan 128 MB de memoria; el panel mensual son 9,87 M de filas |
| Entrenamiento de modelos | **Local** | 860 mil clientes × 73 variables; el techo de CPU son 30 s |
| Notebooks | **Local** | No hay equivalente en Cloudflare |
| Tablero Streamlit | **Local** | Es un proceso vivo con WebSocket; los Workers son aislados por petición |
| **Resultados y consulta** | **Cloudflare** | Es exactamente lo que Cloudflare hace bien |

El tablero Streamlit sigue siendo la herramienta del analista. Esto es la
vitrina: rápida, con URL pública y sin nada que instalar para verla.

## Requisitos

- Node.js 18 o superior
- Una cuenta de Cloudflare (el plan gratuito alcanza)

No hace falta ningún token: `wrangler login` autentica por navegador.

## Despliegue

```bash
cd cloudflare
npm install
npx wrangler login
```

**1. Generar los datos** (desde la raíz del proyecto, con el pipeline ya corrido):

```bash
python cloudflare/scripts/generar_seed.py
```

Produce `seed/` con el esquema, los catálogos y los clientes en 9 trozos
(117 MB en total). Esos archivos **no se versionan**: se regeneran.

**2. Crear la base de datos:**

```bash
npx wrangler d1 create crean
```

Imprime un `database_id`. **Péguelo en `wrangler.toml`**, reemplazando
`PEGAR_AQUI_EL_ID_QUE_IMPRIME_WRANGLER`. Sin eso el despliegue falla.

**3. Cargar los datos:**

```bash
npx wrangler d1 execute crean --remote --file=./seed/schema.sql
npx wrangler d1 execute crean --remote --file=./seed/catalogos.sql
```

Y los nueve trozos de clientes. En PowerShell:

```powershell
Get-ChildItem seed/clientes_*.sql | ForEach-Object { npx wrangler d1 execute crean --remote --file=$_.FullName }
```

Toma varios minutos: son 860.223 filas. Verificar al terminar:

```bash
npx wrangler d1 execute crean --remote --command="SELECT COUNT(*) FROM cliente"
```

Debe devolver **860223**.

**4. Publicar:**

```bash
npx wrangler deploy
```

Imprime la URL. Para probar en local antes: `npx wrangler dev`.

## Cómo se respetan los límites de D1

El plan gratuito permite **5 millones de filas leídas por día**. La tabla de
clientes tiene 860.223 filas, así que un solo `SELECT` sin cuidado consumiría
el 17% del presupuesto diario en una sola carga de página. Dos decisiones lo
evitan:

**Los totales salen de una tabla precalculada.** `conteo` tiene 24 filas, una
por combinación de población, nivel y segmento. El total de la lista y su
entrada bruta son una suma sobre un subconjunto de esas 24 filas. Contarlo
sobre `cliente` habría costado 215.057 lecturas en el filtro por defecto.

**La lista elige entre dos caminos según la selectividad.** Recorrer el índice
de percentil en orden cuesta aproximadamente `N × límite / total` filas;
filtrar por el índice compuesto y ordenar cuesta `total`. El cruce está en
`total > √(N × límite)`, y el Worker aplica esa regla. Medido sobre los datos
reales:

| Filtro | Coinciden | Recorriendo el índice | Filtrando y ordenando |
|---|---|---|---|
| Nivel A (por defecto) | 215.057 | **100** | 215.057 |
| Nivel A, preferencial | 11.896 | **152** | 11.896 |
| D + preferencial + sin historial | 47 | 860.223 | **47** |

La regla acierta en los dos extremos. El Worker devuelve en `estrategia` cuál
usó, para poder verificarlo en producción.

## `numero_id` es texto, y no es negociable

El identificador llega a ±9,2 × 10¹⁸. El entero exacto máximo de JavaScript es
9,007 × 10¹⁵, unas mil veces menor. Todo Worker es JavaScript, así que si el
identificador viajara como número, `JSON.parse` le cambiaría los últimos
dígitos **en silencio** y la API devolvería clientes que no existen.

Por eso se guarda como `TEXT` en D1, se valida con una expresión regular sobre
dígitos y nunca pasa por `Number()`. Es la misma razón por la que el CSV del
tablero Streamlit se exporta como texto.

## Verificación previa

D1 es SQLite, así que el volcado se probó localmente antes de subir nada:
carga completa de los 117 MB, las 9 tablas con sus conteos correctos, los
860.223 identificadores únicos e intactos, y las 13 consultas del Worker
ejecutadas contra esa réplica.

Lo que **no** está verificado, porque exige la cuenta: el despliegue en sí, los
tiempos reales de importación a D1 y el comportamiento del binding de assets.
Si `wrangler` se queja de la sección `[assets]`, revisar la sintaxis contra la
documentación de la versión instalada — esa parte de la API cambió
recientemente.

## Estructura

```
wrangler.toml          configuración del Worker y el binding de D1
package.json           wrangler como dependencia de desarrollo
src/index.js           API: 8 rutas, todas con índice y LIMIT
public/index.html      las 7 secciones
public/estilo.css      paleta compartida con el tablero Streamlit
public/app.js          consultas y render, sin framework ni compilación
scripts/generar_seed.py  produce seed/ desde oro.db y outputs/
seed/                  generado, no versionado
```
