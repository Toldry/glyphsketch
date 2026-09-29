import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { buildSite, repositoryUrl } from "../scripts/build_site.ts";

const exported = existsSync(new URL("../../export/glyphsketch-model.bin", import.meta.url));
const built = existsSync(new URL("../dist/demo/demo.js", import.meta.url));

test("the site holds the demo, the engine and the shipped files only", { skip: !(exported && built) && "needs npm run build and an export" }, () => {
  const output = mkdtempSync(join(tmpdir(), "glyphsketch-site-"));
  try {
    buildSite(output);
    for (const path of [
      "index.html", ".nojekyll", "source.json", "web/demo/index.html", "web/demo/style.css", "web/demo/favicon.svg",
      "web/demo/manifest.webmanifest", "web/demo/sw.js", "web/demo/icons/icon-192.png",
      "web/demo/icons/icon-512.png", "web/demo/icons/maskable-512.png",
      "web/dist/demo/demo.js", "web/dist/src/index.js", "web/dist/src/model.js",
      "export/glyphsketch-model.bin", "export/glyphsketch-index.bin", "export/glyphsketch-charset.json",
      "export/Unicode-3.0.txt",
    ]) {
      assert.ok(existsSync(join(output, path)), path);
    }
    for (const path of ["export/glyphsketch.onnx", "export/fixtures.json", "web/dist/test", "web/dist/scripts"]) {
      assert.ok(!existsSync(join(output, path)), `${path} should not be published`);
    }
    assert.match(readFileSync(join(output, "index.html"), "utf-8"), /url=web\/demo\//);
    assert.doesNotMatch(readFileSync(join(output, "web/demo/sw.js"), "utf-8"), /VERSION = "dev"/);
  } finally {
    rmSync(output, { recursive: true, force: true });
  }
});

test("repository URLs come from GitHub Actions or the origin remote", () => {
  assert.equal(repositoryUrl(null, "someone/glyphsketch"), "https://github.com/someone/glyphsketch");
  assert.equal(repositoryUrl("git@github.com:someone/glyphsketch.git"), "https://github.com/someone/glyphsketch");
  assert.equal(repositoryUrl("https://github.com/someone/glyphsketch.git"), "https://github.com/someone/glyphsketch");
  assert.equal(repositoryUrl("https://example.org/x.git"), null);
  assert.equal(repositoryUrl(null), null);
});

test("the service worker caches every compiled module of the engine and the demo", { skip: !built && "needs npm run build" }, () => {
  const worker = readFileSync(new URL("../demo/sw.js", import.meta.url), "utf-8");
  for (const part of ["demo", "src"]) {
    const directory = new URL(`../dist/${part}/`, import.meta.url);
    for (const name of readdirSync(directory).filter((file) => file.endsWith(".js"))) {
      assert.ok(worker.includes(`"../dist/${part}/${name}"`), `sw.js should cache ${part}/${name}`);
    }
  }
});
