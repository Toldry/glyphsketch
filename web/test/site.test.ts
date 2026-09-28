import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
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
      "index.html", ".nojekyll", "source.json", "web/demo/index.html", "web/demo/style.css",
      "web/dist/demo/demo.js", "web/dist/src/index.js", "web/dist/src/model.js",
      "export/glyphsketch-model.bin", "export/glyphsketch-index.bin", "export/glyphsketch-charset.json",
    ]) {
      assert.ok(existsSync(join(output, path)), path);
    }
    for (const path of ["export/glyphsketch.onnx", "export/fixtures.json", "web/dist/test", "web/dist/scripts"]) {
      assert.ok(!existsSync(join(output, path)), `${path} should not be published`);
    }
    assert.match(readFileSync(join(output, "index.html"), "utf-8"), /url=web\/demo\//);
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
