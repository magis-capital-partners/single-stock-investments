# Magis CI Autofix

This package triages failed GitHub Actions runs, notifies Slack, and dispatches a Cursor Cloud Agent for failures that look code-fixable.

## Secrets

Set these repository or organization secrets:

- `CURSOR_API_KEY`: Cursor Cloud Agent API key.
- `SLACK_WEBHOOK_URL`: Slack incoming webhook URL.

If `SLACK_WEBHOOK_URL` is missing, the workflow still creates GitHub issues for notify-only failures. If `CURSOR_API_KEY` is missing, it will notify that Cursor dispatch is disabled.

## Slack setup

1. In Slack, create an app at <https://api.slack.com/apps>.
2. Enable **Incoming Webhooks**.
3. Add a webhook to the desired channel.
4. Copy the webhook URL.
5. In GitHub, set it as an org secret:

```powershell
gh secret set SLACK_WEBHOOK_URL --org magis-capital-partners --visibility all
```

Then set Cursor:

```powershell
gh secret set CURSOR_API_KEY --org magis-capital-partners --visibility all
```

## Current repo

This repo has a local `.github/workflows/ci-autofix.yml` that runs `_system/ci_autofix/ci_autofix.mjs` directly.

## Org-wide rollout

After fixing GitHub CLI auth, run:

```powershell
gh auth login -h github.com
powershell -ExecutionPolicy Bypass -File _system/ci_autofix/install_org_repos.ps1 -Org magis-capital-partners
```

Use `-DryRun` first to inspect local branches without pushing:

```powershell
powershell -ExecutionPolicy Bypass -File _system/ci_autofix/install_org_repos.ps1 -Org magis-capital-partners -DryRun
```

The installer opens one draft PR per non-archived repo. It copies this package into each repo instead of depending on cross-repo private workflow access.

## External poller

The GitHub Actions workflow cannot run if GitHub refuses to start jobs because of billing, spending-limit, or runner capacity issues. Use the external poller on a machine or VM you control to catch those failures:

```powershell
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
$env:CURSOR_API_KEY = "cursor-api-key"
gh auth login -h github.com
powershell -ExecutionPolicy Bypass -File _system/ci_autofix/poll_org_failures.ps1 -Org magis-capital-partners -LookbackHours 24
```

For continuous monitoring, run that command every 10-15 minutes from Windows Task Scheduler, cron, launchd, or a small VM scheduler. The poller stores handled run IDs in:

```text
%USERPROFILE%\.magis-ci-autofix-state.json
```

## Classification

Notify-only by default:

- GitHub Actions billing/spending/runner startup failures
- missing secrets or invalid credentials
- permission failures
- fork PR failures
- no usable logs

Cursor dispatch by default:

- test failures
- build failures
- type/lint failures
- generated artifact drift
- workflow logic bugs with actionable logs
