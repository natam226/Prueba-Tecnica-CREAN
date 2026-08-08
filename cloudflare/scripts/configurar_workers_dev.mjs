import { readFileSync } from "node:fs";
import { join } from "node:path";

const [subdomain = "crean-tablero", scriptName = "crean-tablero"] =
  process.argv.slice(2);
const accountId =
  process.env.CLOUDFLARE_ACCOUNT_ID || "ab685c7ea9a5500ea5ed18450ca6fd92";

function tokenWrangler() {
  if (process.env.CLOUDFLARE_API_TOKEN) return process.env.CLOUDFLARE_API_TOKEN;

  const appData = process.env.APPDATA;
  if (!appData) throw new Error("No existe APPDATA para ubicar Wrangler.");

  const config = readFileSync(
    join(appData, "xdg.config", ".wrangler", "config", "default.toml"),
    "utf8"
  );
  const m = config.match(/^oauth_token\s*=\s*"([^"]+)"/m);
  if (!m) {
    throw new Error("Wrangler no tiene oauth_token. Corre `wrangler login`.");
  }
  return m[1];
}

async function llamar(path, init = { method: "GET" }) {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}${path}`,
    {
      ...init,
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
    }
  );
  const data = await resp.json();
  if (!resp.ok || data.success === false) {
    const detalle = data.errors?.map((e) => e.message).join("; ");
    throw new Error(`${init.method} ${path} fallo: ${detalle || resp.status}`);
  }
  return data.result;
}

const token = tokenWrangler();

let cuenta;
try {
  cuenta = await llamar("/workers/subdomain");
} catch {
  cuenta = await llamar("/workers/subdomain", {
    method: "PUT",
    body: JSON.stringify({ subdomain }),
  });
}
console.log(`Subdominio de cuenta: ${cuenta.subdomain}.workers.dev`);

const worker = await llamar(`/workers/scripts/${scriptName}/subdomain`, {
  method: "POST",
  body: JSON.stringify({ enabled: true, previews_enabled: true }),
});
console.log(
  `workers.dev para ${scriptName}: enabled=${worker.enabled}, previews=${worker.previews_enabled}`
);
