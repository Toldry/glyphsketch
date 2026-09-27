/**
 * Static server for the demo: serves web/ and export/ from the repository root, nothing
 * else. Usage: npm run serve (builds first), then open http://localhost:5173/web/demo/.
 */

import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const ALLOWED = ["web", "export"];
const PORT = Number(process.env.PORT ?? 5173);
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".bin": "application/octet-stream",
};

createServer((request, response) => {
  const path = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
  if (path === "/") {
    response.writeHead(302, { Location: "/web/demo/" }).end();
    return;
  }
  let file = resolve(ROOT, normalize(`.${path}`));
  const top = file.slice(ROOT.length).split(sep)[0] ?? "";
  if (!file.startsWith(ROOT) || !ALLOWED.includes(top)) {
    response.writeHead(404).end("Not found");
    return;
  }
  try {
    if (statSync(file).isDirectory()) file = resolve(file, "index.html");
    statSync(file);
  } catch {
    response.writeHead(404).end("Not found");
    return;
  }
  response.writeHead(200, {
    "Content-Type": TYPES[extname(file)] ?? "application/octet-stream",
    "Cache-Control": "no-cache",
  });
  createReadStream(file).pipe(response);
}).listen(PORT, () => {
  console.log(`glyphsketch demo: http://localhost:${PORT}/web/demo/`);
});
