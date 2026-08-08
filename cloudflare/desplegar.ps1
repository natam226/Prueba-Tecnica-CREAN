# Despliegue completo del tablero CREAN en Cloudflare.
#
#   cd cloudflare
#   .\desplegar.ps1
#
# Hace todo de corrido: instala wrangler, crea la base D1, pega el id en
# wrangler.toml, carga las 860.223 filas y publica.
#
# AUTENTICACION -- dos caminos, elige uno:
#
#   a) Interactivo (recomendado): no hagas nada. El script llama a
#      `wrangler login`, que abre el navegador. Nunca escribes una llave.
#
#   b) Con token: si ya tienes uno en tu .env, exportalo TU antes de correr
#      esto y el script lo detecta:
#
#          $env:CLOUDFLARE_API_TOKEN = "tu-token"
#          .\desplegar.ps1
#
#      wrangler lee esa variable por si sola.
#
# NOTA: este script no se pudo probar de punta a punta, porque ejecutarlo
# requiere una cuenta de Cloudflare. Cada paso se detiene si falla, asi que
# no deberia dejar nada a medias.

$ErrorActionPreference = "Stop"
$BASE = "crean"

function Paso($n, $texto) {
    Write-Host ""
    Write-Host "[$n] $texto" -ForegroundColor Cyan
}

# --- 0. Requisitos --------------------------------------------------------
Paso 0 "Comprobando requisitos"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Falta Node.js 18 o superior: https://nodejs.org" -ForegroundColor Red
    exit 1
}
Write-Host "  node $(node --version)"
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    if (Get-Command corepack -ErrorAction SilentlyContinue) {
        corepack enable
    }
}
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Write-Host "Falta pnpm. Con Node reciente suele bastar: corepack enable" -ForegroundColor Red
    exit 1
}
Write-Host "  pnpm $(pnpm --version)"

if (-not (Test-Path "seed/schema.sql")) {
    Write-Host "  Falta seed/. Generandolo..." -ForegroundColor Yellow
    Push-Location ..
    & "venv/Scripts/python.exe" cloudflare/scripts/generar_seed.py
    Pop-Location
}
$trozos = Get-ChildItem "seed/clientes_*.sql" | Sort-Object Name
Write-Host "  seed listo: $($trozos.Count) archivos de clientes"

# Cargar 117 MB a D1 y descubrir despues que el volcado estaba mal es caro en
# tiempo y en cuota de escritura. Se comprueba antes, contra un SQLite local.
Write-Host "  Verificando el volcado..."
Push-Location ..
& "venv/Scripts/python.exe" cloudflare/scripts/verificar_seed.py
$verificacion = $LASTEXITCODE
Pop-Location
if ($verificacion -ne 0) { throw "el volcado no paso la verificacion; no se sube nada" }

# --- 1. Dependencias ------------------------------------------------------
Paso 1 "Instalando wrangler"
pnpm install --frozen-lockfile
if ($LASTEXITCODE -ne 0) { throw "pnpm install fallo" }

# --- 2. Autenticacion -----------------------------------------------------
Paso 2 "Autenticando contra Cloudflare"
if ($env:CLOUDFLARE_API_TOKEN) {
    Write-Host "  Usando CLOUDFLARE_API_TOKEN del entorno."
} else {
    Write-Host "  Abriendo el navegador para autorizar..."
    pnpm exec wrangler login
    if ($LASTEXITCODE -ne 0) { throw "wrangler login fallo" }
}

# --- 3. Base de datos -----------------------------------------------------
Paso 3 "Creando la base D1 '$BASE'"
$existentes = pnpm exec wrangler d1 list --json 2>$null | ConvertFrom-Json
$db = $existentes | Where-Object { $_.name -eq $BASE }
if ($db) {
    Write-Host "  Ya existia, se reutiliza."
} else {
    pnpm exec wrangler d1 create $BASE
    if ($LASTEXITCODE -ne 0) { throw "no se pudo crear la base" }
    $db = (pnpm exec wrangler d1 list --json | ConvertFrom-Json) |
          Where-Object { $_.name -eq $BASE }
}
$id = $db.uuid
if (-not $id) { throw "no se pudo obtener el database_id" }
Write-Host "  database_id: $id"

Paso 4 "Escribiendo el id en wrangler.toml"
$toml = Get-Content wrangler.toml -Raw
$toml = $toml -replace 'database_id\s*=\s*"[^"]*"', "database_id = `"$id`""
Set-Content wrangler.toml $toml -Encoding utf8 -NoNewline
Write-Host "  hecho"

# --- 5. Carga -------------------------------------------------------------
Paso 5 "Cargando el esquema y los catalogos"
pnpm exec wrangler d1 execute $BASE --remote --file="./seed/schema.sql" --yes
if ($LASTEXITCODE -ne 0) { throw "fallo la carga del esquema" }
pnpm exec wrangler d1 execute $BASE --remote --file="./seed/catalogos.sql" --yes
if ($LASTEXITCODE -ne 0) { throw "fallo la carga de catalogos" }

Paso 6 "Cargando 860.223 clientes en $($trozos.Count) trozos (toma varios minutos)"
$i = 0
foreach ($t in $trozos) {
    $i++
    Write-Host "  [$i/$($trozos.Count)] $($t.Name)"
    pnpm exec wrangler d1 execute $BASE --remote --file=$($t.FullName) --yes
    if ($LASTEXITCODE -ne 0) { throw "fallo cargando $($t.Name)" }
}

# --- 7. Verificacion ------------------------------------------------------
Paso 7 "Verificando la carga"
pnpm exec wrangler d1 execute $BASE --remote --command="SELECT COUNT(*) AS clientes FROM cliente"
Write-Host "  Debe decir 860223. Si dice menos, vuelve a correr el paso 6." -ForegroundColor Yellow

# --- 8. Publicacion -------------------------------------------------------
Paso 8 "Publicando el Worker"
pnpm exec wrangler deploy
if ($LASTEXITCODE -ne 0) { throw "el despliegue fallo" }

Write-Host ""
Write-Host "Listo. La URL aparece arriba, en la salida de wrangler deploy." -ForegroundColor Green
Write-Host "Pruebala y comparte el enlace si quieres que verifique que responde bien."
