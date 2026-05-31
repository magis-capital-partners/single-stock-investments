#!/usr/bin/env node
/**
 * Run Marvin company deep dive via Cursor Cloud Agent.
 * Opens a PR with research outputs — human review before merge.
 *
 * Prompt source of truth: _system/prompts/cloud_marvin_runbook.md
 * Mechanical pipeline: _system/scripts/marvin_cloud_refresh.py
 *
 * Env:
 *   CURSOR_API_KEY  — required (repo secret)
 *   TICKER          — required (e.g. 8697.T)
 *   GITHUB_REPOSITORY — owner/repo (set automatically in Actions)
 *   PICK_REASON     — optional (new_documents, new_valuation_news, manual, …)
 */
import { readFileSync } from "node:fs";
import { Agent, CursorAgentError } from "@cursor/sdk";

const ticker = process.env.TICKER?.trim();
const apiKey = process.env.CURSOR_API_KEY?.trim();
const repo = process.env.GITHUB_REPOSITORY?.trim();
const pickReason = process.env.PICK_REASON?.trim() || "scheduled";
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

const prefix = readFileSync("_system/prompts/_prefix.md", "utf8");
let runbook = readFileSync("_system/prompts/cloud_marvin_runbook.md", "utf8");
runbook = runbook
  .replaceAll("{{TICKER}}", ticker)
  .replaceAll("{{date}}", date)
  .replaceAll("{{PICK_REASON}}", pickReason);

const prompt = `${prefix}

${runbook}

---

**Cloud agent reminder:** You MUST finish by running:
\`python _system/scripts/marvin_cloud_refresh.py ${ticker} --date ${date}\`
after narrative + valuation.json updates. Do not hand-merge valuation sections; \`refresh_deep_dive_v2.py\` owns structure.
`;

const repoUrl = `https://github.com/${repo}`;

try {
  console.log(`Starting Marvin deep dive for ${ticker} on ${repoUrl}...`);
  const result = await Agent.prompt(prompt, {
    apiKey,
    model: { id: "composer-2.5" },
    cloud: {
      repos: [{ url: repoUrl }],
      autoCreatePR: true,
      skipReviewerRequest: true,
    },
  });

  console.log("Status:", result.status);
  console.log("Agent ID:", result.agentId);
  if (result.prUrl) console.log("PR:", result.prUrl);
  if (result.result) console.log("Summary:", result.result.slice(0, 500));

  if (result.status === "error") {
    console.error("Agent run failed.");
    process.exit(2);
  }
} catch (err) {
  if (err instanceof CursorAgentError) {
    console.error("Startup failed:", err.message, "retryable=", err.isRetryable);
    process.exit(1);
  }
  throw err;
}
