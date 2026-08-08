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

- Node.js 24 o superior
- pnpm 11.16.0 (`corepack enable` lo activa en instalaciones recientes de Node)
- Una cuenta de Cloudflare (el plan gratuito alcanza)

Para el despliegue manual **no hace falta ningún token**: `wrangler login`
autentica por navegador. El token solo se necesita para el despliegue
automático desde GitHub Actions (ver más abajo), porque allí no hay un
navegador donde autorizar.

El proyecto usa `pnpm-lock.yaml` versionado. CI y despliegue local instalan con
`pnpm install --frozen-lockfile`, así Wrangler y sus dependencias quedan
fijadas.

## Despliegue

```bash
cd cloudflare
corepack enable
pnpm install --frozen-lockfile
pnpm exec wrangler login
```

**1. Generar los datos** (desde la raíz del proyecto, con el pipeline ya corrido):

```bash
python cloudflare/scripts/generar_seed.py
```

Produce `seed/` con el esquema, los catálogos y los clientes en 9 trozos
(117 MB en total). Esos archivos **no se versionan**: se regeneran.

**2. Crear la base de datos:**

```bash
pnpm exec wrangler d1 create crean
```

Imprime un `database_id`. **Péguelo en `wrangler.toml`**, reemplazando
`PEGAR_AQUI_EL_ID_QUE_IMPRIME_WRANGLER`. Sin eso el despliegue falla.

**3. Cargar los datos:**

```bash
pnpm exec wrangler d1 execute crean --remote --file=./seed/schema.sql
pnpm exec wrangler d1 execute crean --remote --file=./seed/catalogos.sql
```

Y los nueve trozos de clientes. En PowerShell:

```powershell
Get-ChildItem seed/clientes_*.sql | ForEach-Object { pnpm exec wrangler d1 execute crean --remote --file=$_.FullName }
```

Toma varios minutos: son 860.223 filas. Verificar al terminar:

```bash
pnpm exec wrangler d1 execute crean --remote --command="SELECT COUNT(*) FROM cliente"
```

Debe devolver **860223**.

**4. Publicar:**

```bash
pnpm exec wrangler deploy
```

Imprime la URL. Para probar en local antes: `pnpm exec wrangler dev`.

Estado actual: la base D1 `crean` ya existe con
`database_id = "45ca7c15-30ae-4b09-95a7-8880b4b4e5e0"` y el Worker publico
esta en `https://crean-tablero.crean-tablero.workers.dev`.

## Despliegue automático desde GitHub

`.github/workflows/ci.yml` prueba, empaqueta y publica **en cada push a
`main`**, y solo eso: no corre en ramas ni en pull requests.

Cada trabajo se salta solo si su área no cambió, que es lo que significa
«desplegar lo que haya cambiado»:

| Se tocó | `prueba` | `construir` | `desplegar` |
|---|---|---|---|
| `app/`, `src/`, `tests/`, `config.py`… | sí | — | — |
| `cloudflare/` | — | sí | sí |
| ambos | sí | sí | sí |
| solo `docs/`, `README.md`, notebooks | — | — | — |

Una prueba **saltada** deja pasar el despliegue; una prueba **fallida** lo
detiene. Esa distinción exige `!failure() && !cancelled()` en vez del
`success()` implícito, porque con `success()` un trabajo saltado arrastraría
también al que depende de él.

### Lo que hay que configurar una sola vez

Estos tres pasos los tiene que hacer una persona con acceso a las dos cuentas;
no se pueden automatizar desde el repositorio.

**1. Crear el token en Cloudflare.** En *My Profile → API Tokens → Create
Token*, plantilla **Edit Cloudflare Workers**, y añadir el permiso
`Account → D1 → Edit`. Copiarlo: solo se muestra una vez.

**2. Guardarlo como secreto de GitHub.** En el repositorio, *Settings → Secrets
and variables → Actions → New repository secret*:

| Nombre | Qué es | ¿Obligatorio? |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | el token del paso 1 | sí |
| `CLOUDFLARE_ACCOUNT_ID` | id de la cuenta | solo si el token alcanza más de una cuenta |

**3. Dejar resuelto el `database_id`.** El workflow falla con un mensaje claro
si `wrangler.toml` sigue con el marcador de posición. Dos formas, cualquiera
sirve:

- pegar el id que imprimió `wrangler d1 create crean` en `wrangler.toml` y
  versionarlo, o
- guardarlo como **variable** de repositorio `CLOUDFLARE_D1_DATABASE_ID`
  (*Variables*, no *Secrets*) y el workflow lo sustituye al vuelo.

El `database_id` **no es una credencial**: es un identificador y sin el token
no da acceso a nada. Puede vivir en el repositorio sin problema.

### El workflow no carga datos, a propósito

Publica código; nunca toca la tabla `cliente`. No podría aunque quisiera: el
volcado son 117 MB que no están versionados, y generarlo exige `oro/data/oro.db`,
que tampoco lo está. La carga de las 860.223 filas es una operación local y de
una sola vez.

La consecuencia práctica: **cuando se vuelve a correr el pipeline hay que
regenerar el volcado y recargar D1 a mano**. Si no, la web sigue mostrando los
resultados de la corrida anterior mientras el código ya cambió.

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

| Filtro (límite 100) | Coinciden | Recorriendo el índice | Filtrando y ordenando |
|---|---|---|---|
| Nivel A (por defecto) | 215.057 | **400** | 215.057 |
| Nivel A, preferencial | 11.903 | **7.227** | 11.903 |
| D + preferencial + sin historial | 48 | 860.223 | **48** |

En negrita, el camino que elige la regla. Acierta en los dos extremos: en el
último, recorrer el índice acabaría leyendo la tabla entera para encontrar 48
clientes. El Worker devuelve en `estrategia` cuál usó, para poder verificarlo
en producción.

Las tres filas las mide `scripts/verificar_seed.py`; no están escritas a mano.

## `numero_id` es texto, y no es negociable

El identificador llega a ±9,2 × 10¹⁸. El entero exacto máximo de JavaScript es
9,007 × 10¹⁵, unas mil veces menor. Todo Worker es JavaScript, así que si el
identificador viajara como número, `JSON.parse` le cambiaría los últimos
dígitos **en silencio** y la API devolvería clientes que no existen.

Por eso se guarda como `TEXT` en D1, se valida con una expresión regular sobre
dígitos y nunca pasa por `Number()`. Es la misma razón por la que el CSV del
tablero Streamlit se exporta como texto.

## Verificación previa

D1 es SQLite, así que el volcado se prueba localmente antes de subir nada:

```bash
python cloudflare/scripts/verificar_seed.py
```

Carga los 117 MB en una réplica y comprueba las 860.223 filas, las 10 tablas,
los identificadores únicos e intactos, que los totales precalculados de
`conteo` cuadren **combinación por combinación** con `cliente`, que ambos
índices sean utilizables, que la regla de selectividad elija el camino barato
en los tres casos, y que las cifras publicadas coincidan con las del tablero.

Conviene correrlo después de cada `generar_seed.py`: el volcado se queda viejo
en silencio cuando se vuelve a ejecutar el pipeline.

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
scripts/generar_seed.py    produce seed/ desde oro.db y outputs/
scripts/verificar_seed.py  carga seed/ en un SQLite y prueba las consultas
seed/                  generado, no versionado
```

El workflow vive fuera de esta carpeta, en `.github/workflows/ci.yml`.
