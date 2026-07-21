#!/usr/bin/env node
/** Run exactly one isolated Investment Committee task via Cursor Cloud Agent. */
import { readFileSync } from "node:fs";
import { Agent, Cursor, CursorAgentError } from "@cursor/sdk";

const apiKey = process.env.CURSOR_API_KEY?.trim();
const repo = process.env.GITHUB_REPOSITORY?.trim();
const startingRef = process.env.CURSOR_STARTING_REF?.trim();
const promptPath = process.env.PROMPT_PATH?.trim();
const outputPath = process.env.OUTPUT_PATH?.trim();
const taskKey = process.env.TASK_KEY?.trim();
// Model ladder (_system/config/llm_usage_policy.json): chair synthesis runs on
// the frontier model via `llm_call_gate.py model`; rater votes stay cheap.
const modelId = process.env.CURSOR_MODEL_ID?.trim() || "composer-2.5";

for (const [name, value] of Object.entries({ CURSOR_API_KEY: apiKey, GITHUB_REPOSITORY: repo, PROMPT_PATH: promptPath, OUTPUT_PATH: outputPath, TASK_KEY: taskKey })) {
  if (!value) {
    console.error(`${name} is required.`);
    process.exit(1);
  }
}

const stagePrompt = readFileSync(promptPath, "utf8");
const prompt = `You are one isolated Investment Committee method task.

Task key: ${taskKey}
Prompt source: ${promptPath}
Required output: ${outputPath}

${stagePrompt}

Isolation and delivery rules:
1. Read only the evidence and prior-stage files explicitly allowed by the prompt.
2. Never inspect another rater's vote unless this is a later reconciliation/chair task that explicitly requires it.
3. Do not edit valuation inputs, the frozen manifest, a human decision, or another task's output.
4. Write exactly one valid JSON object to ${outputPath}.
5. Run: python _system/scripts/investment_committee_pipeline.py validate ${process.env.TICKER} --date ${process.env.COMMITTEE_DATE} when validation is applicable; missing later-stage files are expected before the final stage.
6. Open a PR titled "${taskKey}". Do not perform any capital decision or sizing.
`;

try {
  const repoSpec = startingRef ? { url: `https://github.com/${repo}`, startingRef } : { url: `https://github.com/${repo}` };
  // Cloud catalog requires a full id+params variant (GET /v1/models).
  // Default Sonnet 5 variant: thinking=true, context=1m, effort=high.
  const model =
    modelId === "claude-sonnet-5"
      ? {
          id: modelId,
          params: [
            { id: "thinking", value: "true" },
            { id: "context", value: "1m" },
            { id: "effort", value: "high" },
          ],
        }
      : { id: modelId };
  const result = await Agent.prompt(prompt, {
    apiKey,
    model,
    cloud: { repos: [repoSpec], autoCreatePR: true, skipReviewerRequest: true },
  });
  console.log("Status:", result.status);
  console.log("Agent ID:", result.agentId);
  if (result.prUrl) console.log("PR:", result.prUrl);
  if (result.status === "error") process.exit(2);
} catch (err) {
  if (err instanceof CursorAgentError) {
    console.error("Startup failed:", err.message, "retryable=", err.isRetryable);
    if (/not available or invalid/i.test(err.message || "")) {
      try {
        const models = await Cursor.models.list({ apiKey });
        const ids = (Array.isArray(models) ? models : models?.items || [])
          .map((row) => row?.model?.id || row?.id || row)
          .filter(Boolean);
        console.error("Available Cursor model ids:", ids.join(", ") || JSON.stringify(models));
      } catch (listErr) {
        console.error("Could not list Cursor models:", listErr?.message || listErr);
      }
    }
    process.exit(1);
  }
  throw err;
}
