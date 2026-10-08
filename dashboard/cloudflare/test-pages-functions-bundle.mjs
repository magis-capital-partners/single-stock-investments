import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../..", import.meta.url));
const wrangler = fileURLToPath(new URL("./node_modules/.bin/wrangler", import.meta.url));
const stageScript = fileURLToPath(new URL("../../_system/scripts/stage_pages_functions.py", import.meta.url));

function pythonBin() {
  for (const bin of ["python3", "python"]) {
    const probe = spawnSync(bin, ["--version"], { encoding: "utf8" });
    if (probe.status === 0) return bin;
  }
  throw new Error("python is required to stage Pages functions");
}

test("repo imports for overlap and time-average resolve", async () => {
  await import("../functions/api/v1/research/overlap.js");
  await import("../functions/api/v1/sleeves/time-average.js");
});

test("wrangler pages functions build resolves the staged routes", () => {
  const dest = mkdtempSync(join(tmpdir(), "pages-functions-"));
  const stage = spawnSync(pythonBin(), [stageScript, dest], { encoding: "utf8" });
  assert.equal(stage.status, 0, stage.stderr || stage.stdout);
  const outdir = join(dest, "out");
  const build = spawnSync(wrangler, [
    "pages", "functions", "build", "functions",
    "--outdir", outdir,
    "--compatibility-date", "2026-08-17",
    "--compatibility-flag", "nodejs_compat",
  ], { cwd: dest, encoding: "utf8" });
  assert.equal(build.status, 0, `${build.stdout}\n${build.stderr}`);
  const bundle = readFileSync(join(outdir, "index.js"), "utf8");
  assert.ok(statSync(join(outdir, "index.js")).size > 1_000_000);
  for (const name of ["overlap_holdings.json", "time_average_growth_params.json"]) {
    const payload = JSON.parse(readFileSync(join(root, "dashboard", "data", name), "utf8"));
    assert.equal(bundle.includes(payload.built_at), true, name);
  }
});
