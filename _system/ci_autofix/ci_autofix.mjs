#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import process from "node:process";
import YAML from "yaml";
import { Agent, CursorAgentError } from "@cursor/sdk";

const repo = process.env.GITHUB_REPOSITORY;
const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
const runId = process.env.CI_AUTOFIX_RUN_ID;
const cursorApiKey = process.env.CURSOR_API_KEY;
const slackWebhookUrl = process.env.SLACK_WEBHOOK_URL;
const forceAgent = String(process.env.CI_AUTOFIX_FORCE_AGENT || "false").toLowerCase() === "true";
const eventPath = process.env.GITHUB_EVENT_PATH;
const config = loadConfig();

if (!repo) fail("GITHUB_REPOSITORY is required.");
if (!token) fail("GITHUB_TOKEN/GH_TOKEN is required.");
if (!runId) fail("CI_AUTOFIX_RUN_ID is required.");

const [owner, name] = repo.split("/");
const repoUrl = `https://github.com/${repo}`;

main().catch(async (err) => {
  console.error(err);
  await notifySlack({
    level: "error",
    title: `CI Autofix crashed in ${repo}`,
    text: err?.stack || err?.message || String(err),
  });
  process.exit(1);
});

async function main() {
  if (config.enabled === false) {
    console.log("CI Autofix disabled by .github/ci-autofix.yml");
    return;
  }

  const run = await github(`/repos/${owner}/${name}/actions/runs/${runId}`);
  const jobs = await getJobs();
  const failedJobs = jobs.filter((job) => ["failure", "cancelled", "timed_out", "startup_failure"].includes(job.conclusion));
  const failedLog = getFailedLog();
  const event = readEvent();
  const skippedWorkflow = (config.cursor?.skip_workflows || []).includes(run.name);
  const forkPr = isForkPullRequest(run, event);
  const classification = classifyFailure({ run, failedJobs, failedLog, skippedWorkflow, forkPr });
  const runUrl = run.html_url || `${repoUrl}/actions/runs/${runId}`;
  const summary = makeSummary({ run, failedJobs, failedLog, classification, runUrl });

  console.log(summary);

  const labels = config.github?.issue_labels || ["ci-autofix", "needs-attention"];
  const shouldNotifyOnly = classification.action === "notify_only" && config.github?.create_issue_for_notify_only !== false;
  if (shouldNotifyOnly) {
    await createIssue({
      title: `[ci-autofix] ${repo}: ${run.name} failed (${classification.category})`,
      body: summary,
      labels,
    });
  }

  await notifySlack({
    level: classification.action === "cursor_agent" ? "warning" : "info",
    title: `${repo}: ${run.name} failed`,
    text: summary,
    runUrl,
    category: classification.category,
  });

  if (classification.action !== "cursor_agent" && !forceAgent) {
    console.log(`No Cursor dispatch: ${classification.reason}`);
    return;
  }

  if (!cursorApiKey) {
    const text = `${summary}\n\nCursor was not dispatched because CURSOR_API_KEY is not configured.`;
    await createIssue({
      title: `[ci-autofix] ${repo}: Cursor not configured for ${run.name}`,
      body: text,
      labels,
    });
    await notifySlack({
      level: "warning",
      title: `${repo}: Cursor not configured`,
      text,
      runUrl,
      category: "configuration",
    });
    return;
  }

  const agentResult = await dispatchCursor({ run, failedJobs, failedLog, classification, runUrl });
  const agentText = [
    `Cursor Cloud Agent dispatched for ${repo}.`,
    `Workflow: ${run.name}`,
    `Run: ${runUrl}`,
    `Agent ID: ${agentResult.agentId || "unknown"}`,
    agentResult.prUrl ? `PR: ${agentResult.prUrl}` : "PR: not returned by Cursor",
    agentResult.status ? `Status: ${agentResult.status}` : "",
    agentResult.result ? `Summary: ${agentResult.result.slice(0, 1200)}` : "",
  ].filter(Boolean).join("\n");

  await notifySlack({
    level: "success",
    title: `${repo}: Cursor agent dispatched`,
    text: agentText,
    runUrl,
    category: "cursor_agent",
  });
}

function loadConfig() {
  const path = ".github/ci-autofix.yml";
  if (!existsSync(path)) return {};
  return YAML.parse(readFileSync(path, "utf8")) || {};
}

async function github(path, options = {}) {
  const res = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API ${res.status} ${path}: ${body}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function getJobs() {
  const out = await github(`/repos/${owner}/${name}/actions/runs/${runId}/jobs?per_page=100`);
  return out.jobs || [];
}

function getFailedLog() {
  try {
    const output = execFileSync("gh", ["run", "view", String(runId), "--repo", repo, "--log-failed"], {
      encoding: "utf8",
      maxBuffer: 12 * 1024 * 1024,
      env: { ...process.env, GH_TOKEN: token },
    });
    return truncate(output, config.cursor?.max_log_chars || 45000);
  } catch (err) {
    const fallback = [err?.stdout, err?.stderr, err?.message].filter(Boolean).join("\n");
    try {
      const view = execFileSync("gh", ["run", "view", String(runId), "--repo", repo], {
        encoding: "utf8",
        maxBuffer: 4 * 1024 * 1024,
        env: { ...process.env, GH_TOKEN: token },
      });
      return truncate(`${fallback}\n\n${view}`, config.cursor?.max_log_chars || 45000);
    } catch (viewErr) {
      const viewFallback = [viewErr?.stdout, viewErr?.stderr, viewErr?.message].filter(Boolean).join("\n");
      return truncate(`${fallback}\n\n${viewFallback}`, config.cursor?.max_log_chars || 45000);
    }
  }
}

function readEvent() {
  if (!eventPath || !existsSync(eventPath)) return null;
  try {
    return JSON.parse(readFileSync(eventPath, "utf8"));
  } catch {
    return null;
  }
}

function isForkPullRequest(run, event) {
  const payloadRun = event?.workflow_run || {};
  const headRepo = payloadRun.head_repository?.full_name || run.head_repository?.full_name;
  if (!headRepo) return false;
  return headRepo.toLowerCase() !== repo.toLowerCase();
}

function classifyFailure({ run, failedJobs, failedLog, skippedWorkflow, forkPr }) {
  const text = `${run.name}\n${run.conclusion}\n${failedJobs.map((j) => `${j.name} ${j.conclusion}`).join("\n")}\n${failedLog}`.toLowerCase();
  const notifyOnly = new Set(config.classify?.notify_only || ["platform", "credentials", "permissions", "human_required"]);

  const rules = [
    {
      category: "platform",
      reason: "GitHub Actions platform, billing, spending limit, or runner startup failure.",
      patterns: [
        /payments have failed/,
        /billing/,
        /spending limit/,
        /startup_failure/,
        /job was not started/,
        /hosted runner.*unavailable/,
        /no hosted parallelism/,
        /waiting for a runner/,
      ],
    },
    {
      category: "credentials",
      reason: "Missing or invalid secret/token/credential.",
      patterns: [
        /secret .* is not set/,
        /.+\ssecret is not set/,
        /is not configured in settings.*secrets and variables.*actions/,
        /cursor_api_key.*not set/,
        /could not resolve.*secret/,
        /bad credentials/,
        /invalid token/,
        /authentication failed/,
        /unauthorized/,
      ],
    },
    {
      category: "permissions",
      reason: "GitHub token, repository permission, or integration permission issue.",
      patterns: [
        /resource not accessible by integration/,
        /permission denied/,
        /403 forbidden/,
        /not permitted/,
        /insufficient permission/,
      ],
    },
    {
      category: "transient",
      reason: "Likely transient network, registry, API, or timeout failure.",
      patterns: [
        /econnreset/,
        /etimedout/,
        /http 50[234]/,
        /502 bad gateway/,
        /503 service unavailable/,
        /504 gateway timeout/,
        /connection timed out/,
        /rate limit exceeded/,
        /temporarily unavailable/,
      ],
    },
  ];

  if (skippedWorkflow) {
    return { category: "configuration", action: "notify_only", reason: "Workflow is excluded from CI Autofix." };
  }
  if (forkPr && config.cursor?.skip_fork_prs !== false) {
    return { category: "fork_pr", action: "notify_only", reason: "Fork pull request skipped to avoid privileged repair on untrusted code." };
  }

  for (const rule of rules) {
    if (rule.patterns.some((pattern) => pattern.test(text))) {
      const action = notifyOnly.has(rule.category) || (rule.category === "transient" && config.classify?.transient_retry_first !== false)
        ? "notify_only"
        : "cursor_agent";
      return { category: rule.category, action, reason: rule.reason };
    }
  }

  if (!failedLog.trim()) {
    return { category: "no_logs", action: "notify_only", reason: "No failed logs were available for agent context." };
  }

  return { category: "agent_fixable", action: "cursor_agent", reason: "Failure has logs and does not match a notify-only guardrail." };
}

function makeSummary({ run, failedJobs, failedLog, classification, runUrl }) {
  const steps = [];
  for (const job of failedJobs) {
    const failedSteps = (job.steps || [])
      .filter((step) => ["failure", "cancelled", "timed_out"].includes(step.conclusion))
      .map((step) => `  - ${step.name}: ${step.conclusion}`)
      .join("\n");
    steps.push(`- ${job.name}: ${job.conclusion}${failedSteps ? `\n${failedSteps}` : ""}`);
  }

  return [
    `## CI Autofix triage`,
    ``,
    `Repository: ${repo}`,
    `Workflow: ${run.name}`,
    `Run: ${runUrl}`,
    `Branch: ${run.head_branch || "unknown"}`,
    `SHA: ${run.head_sha || "unknown"}`,
    `Conclusion: ${run.conclusion}`,
    `Classification: ${classification.category}`,
    `Action: ${classification.action}`,
    `Reason: ${classification.reason}`,
    ``,
    `### Failed jobs`,
    steps.length ? steps.join("\n") : "No failed job details available.",
    ``,
    `### Log excerpt`,
    "```text",
    truncate(failedLog || "No failed log excerpt available.", 6000),
    "```",
  ].join("\n");
}

async function createIssue({ title, body, labels }) {
  try {
    await ensureLabels(labels);
    const issue = await github(`/repos/${owner}/${name}/issues`, {
      method: "POST",
      body: JSON.stringify({ title, body, labels }),
    });
    console.log(`Created issue: ${issue.html_url}`);
    return issue;
  } catch (err) {
    console.warn(`Could not create issue: ${err.message}`);
    return null;
  }
}

async function ensureLabels(labels = []) {
  for (const label of labels) {
    try {
      await github(`/repos/${owner}/${name}/labels/${encodeURIComponent(label)}`);
    } catch {
      try {
        await github(`/repos/${owner}/${name}/labels`, {
          method: "POST",
          body: JSON.stringify({ name: label, color: label === "needs-attention" ? "d93f0b" : "5319e7" }),
        });
      } catch {
        // Non-fatal. The issue can still be created without labels in some permission configurations.
      }
    }
  }
}

async function notifySlack({ level, title, text, runUrl, category }) {
  if (!slackWebhookUrl || config.slack?.enabled === false) {
    console.log("Slack notification skipped; SLACK_WEBHOOK_URL is not configured or Slack is disabled.");
    return;
  }
  const mention = config.slack?.mention ? `${config.slack.mention} ` : "";
  const color = level === "success" ? "#2eb67d" : level === "error" ? "#e01e5a" : "#ecb22e";
  const payload = {
    text: `${mention}${title}`,
    attachments: [
      {
        color,
        title,
        title_link: runUrl,
        fields: [
          { title: "Repository", value: repo, short: true },
          { title: "Category", value: category || "unknown", short: true },
        ],
        text: truncate(text, 7000),
        mrkdwn_in: ["text"],
      },
    ],
  };
  const res = await fetch(slackWebhookUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.warn(`Slack webhook failed: ${res.status} ${await res.text()}`);
  }
}

async function dispatchCursor({ run, failedJobs, failedLog, classification, runUrl }) {
  const prompt = buildCursorPrompt({ run, failedJobs, failedLog, classification, runUrl });
  const startingRef = run.head_branch || run.head_sha;
  const repoSpec = startingRef ? { url: repoUrl, startingRef } : { url: repoUrl };

  try {
    const result = await Agent.prompt(prompt, {
      apiKey: cursorApiKey,
      model: { id: config.cursor?.model || "composer-2.5" },
      cloud: {
        repos: [repoSpec],
        autoCreatePR: true,
        skipReviewerRequest: true,
        envVars: {
          CI_AUTOFIX_RUN_ID: String(runId),
          CI_AUTOFIX_RUN_URL: runUrl,
        },
      },
    });

    console.log("Cursor status:", result.status);
    console.log("Cursor agent ID:", result.agentId);
    if (result.prUrl) console.log("Cursor PR:", result.prUrl);

    if (result.status === "error") {
      throw new Error(`Cursor agent returned error: ${result.result || "unknown error"}`);
    }
    return result;
  } catch (err) {
    if (err instanceof CursorAgentError) {
      throw new Error(`Cursor startup failed: ${err.message}; retryable=${err.isRetryable}`);
    }
    throw err;
  }
}

function buildCursorPrompt({ run, failedJobs, failedLog, classification, runUrl }) {
  const repoNotes = config.repo_notes ? `\nRepository notes:\n${config.repo_notes}\n` : "";
  const failedJobText = failedJobs.map((job) => {
    const steps = (job.steps || [])
      .filter((step) => step.conclusion && step.conclusion !== "success")
      .map((step) => `  - ${step.name}: ${step.conclusion}`)
      .join("\n");
    return `- ${job.name}: ${job.conclusion}${steps ? `\n${steps}` : ""}`;
  }).join("\n");

  return `You are a senior software engineer fixing a failing GitHub Actions workflow.

Goal:
- Investigate the failed workflow.
- Make the smallest correct code/config/test fix.
- Run the relevant local verification commands if possible.
- Open a draft pull request with a clear title, diagnosis, fix summary, and verification notes.

Guardrails:
- Do not auto-merge.
- Do not make unrelated refactors.
- Do not commit secrets or credentials.
- If the issue is external platform/billing/secrets/permissions and no code fix is possible, open a PR only if you can improve diagnostics or guardrails. Otherwise report clearly.
- Label the PR with: ${(config.github?.pr_labels || ["ci-autofix", "agent-generated", "needs-human-review"]).join(", ")}

Repository: ${repoUrl}
Workflow: ${run.name}
Run URL: ${runUrl}
Branch: ${run.head_branch || "unknown"}
SHA: ${run.head_sha || "unknown"}
Classification: ${classification.category}
Classifier reason: ${classification.reason}
${repoNotes}
Failed jobs:
${failedJobText || "No failed job details available."}

Failed log excerpt:
\`\`\`text
${truncate(failedLog, config.cursor?.max_log_chars || 45000)}
\`\`\`
`;
}

function truncate(value, max) {
  const text = String(value || "");
  if (text.length <= max) return text;
  return `${text.slice(0, Math.floor(max * 0.65))}\n\n... [truncated ${text.length - max} chars] ...\n\n${text.slice(-Math.floor(max * 0.35))}`;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
