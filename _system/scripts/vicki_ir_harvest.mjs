#!/usr/bin/env node
/**
 * Run Vicki IR harvest via Cursor Cloud Agent (browser-capable).
 *
 * Prompt source: _system/prompts/cloud_vicki_runbook.md
 *
 * Env:
 *   CURSOR_API_KEY  — required (repo secret)
 *   TICKER          — required
 *   GITHUB_REPOSITORY — owner/repo (Actions)
 *   PICK_REASON     — optional (ir_gap, manual, …)
 */
import { readFileSync } from "node:fs";
import { Agent, CursorAgentError } from "@cursor/sdk";

const ticker = process.env.TICKER?.trim();
const apiKey = process.env.CURSOR_API_KEY?.trim();
const repo = process.env.GITHUB_REPOSITORY?.trim();
const startingRef = process.env.CURSOR_STARTING_REF?.trim();
const pickReason = process.env.PICK_REASON?.trim() || "ir_gap";
const evidenceHash = process.env.IR_EVIDENCE_HASH?.trim();
const adapterPath = process.env.IR_ADAPTER_PATH?.trim() || `${ticker}/investor-documents/ir_adapter.json`;
const date = new Date().toISOString().slice(0, 10);

if (!apiKey) {
  console.error("CURSOR_API_KEY is required.");
  process.exit(1);
}
if (!ticker) {
  console.error("TICKER is required.");
  process.exit(1);
}
if (!repo) {
  console.error("GITHUB_REPOSITORY is required (owner/repo).");
  process.exit(1);
}

const prefix = readFileSync("_system/prompts/_prefix.md", "utf8")
  .replaceAll("{TICKER}", ticker)
  .replaceAll("{{TICKER}}", ticker);
let runbook = readFileSync("_system/prompts/cloud_vicki_runbook.md", "utf8");
runbook = runbook
  .replaceAll("{{TICKER}}", ticker)
  .replaceAll("{{date}}", date)
  .replaceAll("{{PICK_REASON}}", pickReason);

const prompt = `${prefix}

${runbook}

---

**Cloud agent reminder:** You are Vicki, not Marvin. Focus on browser IR harvest only. Open a PR with PDFs + indexes when done.

This is an exception run for IR evidence hash \`${evidenceHash || "missing"}\`.
First confirm deterministic downloaders cannot complete the job. On success,
write \`${adapterPath}\` with the IR base URL, stable URL patterns, pagination,
document/date selectors, redirect or anti-bot behavior, last_verified date, and
\`deterministic_status: "working"\` plus \`evidence_hash: "${evidenceHash || ""}"\`.
Future harvests must be able to skip Vicki.
`;

const repoUrl = `https://github.com/${repo}`;

try {
  console.log(`Starting Vicki IR harvest for ${ticker} on ${repoUrl}...`);
  console.log(`Starting ref: ${startingRef || "(Cursor default branch)"}`);
  const repoSpec = startingRef ? { url: repoUrl, startingRef } : { url: repoUrl };
  const result = await Agent.prompt(prompt, {
    apiKey,
    // Vicki is a mechanical browser lane; stays on the cheap ladder default.
    model: { id: process.env.CURSOR_MODEL_ID?.trim() || "composer-2.5" },
    cloud: {
      repos: [repoSpec],
      autoCreatePR: true,
      skipReviewerRequest: true,
    },
  });

  console.log("Status:", result.status);
  console.log("Agent ID:", result.agentId);
  if (result.prUrl) console.log("PR:", result.prUrl);
  if (result.result) console.log("Summary:", result.result.slice(0, 500));

  if (result.status === "error") {
    console.error("Vicki agent run failed.");
    process.exit(2);
  }
} catch (err) {
  if (err instanceof CursorAgentError) {
    console.error("CursorAgentError:", err.message);
  } else {
    console.error(err);
  }
  process.exit(1);
}
