# Worker Frontend Streamlit Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajustar el frontend del Worker para recuperar las decisiones utiles del tablero Streamlit sin volverlo pesado.

**Architecture:** Mantener el sitio sin framework ni build step. El contenido estatico sigue en `cloudflare/public/index.html`, la interaccion y llamadas D1 en `cloudflare/public/app.js`, y el lenguaje visual en `cloudflare/public/estilo.css`.

**Tech Stack:** HTML, CSS, JavaScript vanilla, Cloudflare Workers Assets, D1 API existente.

## Global Constraints

- No convertir `numero_id` a numero; siempre se trata como texto.
- No agregar dependencias frontend ni paso de compilacion.
- Mantener la navegacion de 7 secciones.
- Priorizar paridad funcional focalizada con Streamlit: no clonar todo.
- Validar con `node --check`, `wrangler deploy --dry-run`, y endpoints publicos.

---

### Task 1: Estructura visual inspirada en Streamlit

**Files:**
- Modify: `cloudflare/public/index.html`
- Modify: `cloudflare/public/estilo.css`

**Interfaces:**
- Consumes: secciones existentes con ids `resumen`, `clientes`, `solucion`, `oportunidad`, `contactar`, `supuestos`, `operacion`.
- Produces: clases CSS reutilizables `lectura`, `panel-modelo`, `callout-grid`, `mini-diagrama`, `toolbar-secundaria`.

- [ ] **Step 1: Add sidebar/context copy and layout hooks**

Add a second sidebar notice mirroring Streamlit's warning: "Los niveles no se comparan entre grupos." Add wrappers/classes around model and operation blocks so CSS can style them without changing data flow.

- [ ] **Step 2: Add CSS for richer Streamlit-like rhythm**

Implement compact cards for model comparisons, callout grids, progress-like percentiles, and operation diagrams. Keep radius at 6px or less and retain existing palette.

- [ ] **Step 3: Verify layout syntax**

Run: `node --check cloudflare/public/app.js`
Expected: exit 0.

### Task 2: Lista de contacto with Streamlit controls

**Files:**
- Modify: `cloudflare/public/index.html`
- Modify: `cloudflare/public/app.js`
- Modify: `cloudflare/src/index.js`

**Interfaces:**
- Consumes: `/api/clientes` query params `poblacion`, `nivel`, `segmento`, `limit`.
- Produces: `/api/clientes` support for `con_monto=1`; frontend CSV download button.

- [ ] **Step 1: Add filter UI**

Add checkbox `Solo clientes con monto estimado` and button `Descargar CSV` near the existing list filters.

- [ ] **Step 2: Wire filter to API**

When checked, append `con_monto=1` to `/api/clientes`. The Worker already uses `con_inversion = 1`; ensure the `conteo` query and row query use the same condition.

- [ ] **Step 3: Add CSV export**

Generate a UTF-8 CSV from the currently loaded rows. Escape quotes by doubling them, keep `numero_id` as text, and name the file `lista_contacto_crean.csv`.

- [ ] **Step 4: Verify endpoint**

Run: `curl https://crean-tablero.crean-tablero.workers.dev/api/clientes?con_monto=1&limit=3`
Expected: JSON with `filas.length <= 3` and non-null `monto_base_12m` for returned rows.

### Task 3: Ficha de cliente closer to Streamlit

**Files:**
- Modify: `cloudflare/public/index.html`
- Modify: `cloudflare/public/app.js`

**Interfaces:**
- Consumes: `/api/cliente?id=<numero_id>`.
- Produces: richer `#ficha-cliente` rendering with preparation guidance.

- [ ] **Step 1: Add "prepare the call" copy**

Add a short Streamlit-style answer block above the search control explaining that the ficha helps prepare the commercial call.

- [ ] **Step 2: Improve client card**

Render score, group, level, segment, age, model, estimated 12m amount, expected value, and percentile. Do not infer unavailable WOE evidence because the Worker API does not expose it.

- [ ] **Step 3: Add copy-to-search affordance**

When list rows render, make client ids clickable buttons that copy the id into the search input and fetch the ficha.

- [ ] **Step 4: Verify manually through API**

Use one id from `/api/clientes?limit=1`, call `/api/cliente?id=<id>`, and verify the frontend can render all fields without converting the id.

### Task 4: Deployment verification

**Files:**
- Modify: `cloudflare/README.md` if the public behavior changes materially.

**Interfaces:**
- Consumes: local pnpm/wrangler setup already present.
- Produces: deployed Worker version serving the adjusted frontend.

- [ ] **Step 1: Run local syntax checks**

Run: `node --check cloudflare/public/app.js` and `node --check cloudflare/scripts/configurar_workers_dev.mjs`.
Expected: both exit 0.

- [ ] **Step 2: Run Worker dry-run**

Run from `cloudflare`: `wrangler deploy --dry-run --outdir=dist`.
Expected: bindings show `env.DB (crean)` and `env.ASSETS`.

- [ ] **Step 3: Deploy**

Run from `cloudflare`: `wrangler deploy`.
Expected: URL `https://crean-tablero.crean-tablero.workers.dev`.

- [ ] **Step 4: Verify public routes**

Run: `curl -I https://crean-tablero.crean-tablero.workers.dev/`, `curl https://crean-tablero.crean-tablero.workers.dev/api/facetas`, and `curl https://crean-tablero.crean-tablero.workers.dev/api/clientes?con_monto=1&limit=3`.
Expected: HTTP 200 and valid JSON for API routes.

## Self-Review

- Spec coverage: covers Streamlit-inspired rhythm, list controls, CSV download, richer ficha, and deployment verification.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: uses existing endpoint names and existing DOM ids; new classes are CSS-only.
