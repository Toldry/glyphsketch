/**
 * Assemble the static site for GitHub Pages: the demo, the compiled engine and the
 * exported model files, laid out like the repository so the demo's relative paths work.
 *
 * Usage: node scripts/build_site.ts [output directory]   (default: dist/site)
 * Run `npm run build` first (`npm run site` does both).
 */

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB_DIR = fileURLToPath(new URL("../", import.meta.url));
const REPO_DIR = resolve(WEB_DIR, "..");
const EXPORT_FILES = [
  "glyphsketch-model.bin",
  "glyphsketch-index.bin",
  "glyphsketch-charset.json",
  "README.md",
];

const DEMO_FILES = [
  "index.html",
  "style.css",
  "favicon.svg",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/maskable-512.png",
  "icons/apple-touch-icon.png",
];

function git(...args: string[]): string | null {
  try {
    return execFileSync("git", ["-C", REPO_DIR, ...args], {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

/** https://github.com/owner/repo for an origin URL in HTTPS or SSH form. */
export function repositoryUrl(origin: string | null, githubRepository?: string): string | null {
  if (githubRepository) return `https://github.com/${githubRepository}`;
  if (!origin) return null;
  const match = origin.match(/github\.com[:/]([^/]+\/[^/]+?)(?:\.git)?$/);
  return match ? `https://github.com/${match[1]}` : null;
}

function copy(from: string, to: string): void {
  if (!existsSync(from)) throw new Error(`Missing ${from}: run npm run build and the export first`);
  mkdirSync(dirname(to), { recursive: true });
  cpSync(from, to, { recursive: true });
}

export function buildSite(output: string): void {
  rmSync(output, { recursive: true, force: true });
  mkdirSync(output, { recursive: true });
  for (const name of DEMO_FILES) copy(join(WEB_DIR, "demo", name), join(output, "web", "demo", name));
  for (const part of ["demo", "src"]) {
    const from = join(WEB_DIR, "dist", part);
    for (const name of readdirSync(from).filter((file) => file.endsWith(".js") || file.endsWith(".js.map"))) {
      copy(join(from, name), join(output, "web", "dist", part, name));
    }
  }
  for (const name of EXPORT_FILES) copy(join(REPO_DIR, "export", name), join(output, "export", name));
  writeFileSync(
    join(output, "index.html"),
    '<!doctype html>\n<meta charset="utf-8">\n<title>glyphsketch</title>\n' +
      '<link rel="icon" type="image/svg+xml" href="web/demo/favicon.svg">\n' +
      '<meta http-equiv="refresh" content="0; url=web/demo/">\n' +
      '<a href="web/demo/">glyphsketch demo</a>\n',
  );
  writeFileSync(join(output, ".nojekyll"), "");
  const repository = repositoryUrl(git("remote", "get-url", "origin"), process.env["GITHUB_REPOSITORY"]);
  const commit = process.env["GITHUB_SHA"] ?? git("rev-parse", "HEAD");
  // A new service worker per deploy, so installed apps pick up the new files.
  const worker = readFileSync(join(WEB_DIR, "demo", "sw.js"), "utf-8");
  const versioned = worker.replace('const VERSION = "dev";', `const VERSION = "${(commit ?? "unknown").slice(0, 12)}";`);
  if (versioned === worker) throw new Error("sw.js has no VERSION line to replace");
  writeFileSync(join(output, "web", "demo", "sw.js"), versioned);
  writeFileSync(join(output, "source.json"), JSON.stringify({ repository, commit }, null, 1) + "\n");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const output = resolve(process.argv[2] ?? join(WEB_DIR, "dist", "site"));
  buildSite(output);
  console.log(`Site written to ${output}`);
}
