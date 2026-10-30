"""Concurrency groups in .github/workflows must not use `github.job`.

`github.job` is empty when a job-level `concurrency.group` is evaluated, so
`data-commit-main-${{ github.job }}` collapsed every Data Pipeline job into one
queue and newer jobs cancelled pending ones (run 40395625868, 2026-10-26).
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def concurrency_groups() -> list[tuple[str, str, str]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        scopes = [("<workflow>", data.get("concurrency"))]
        scopes += [(name, job.get("concurrency")) for name, job in (data.get("jobs") or {}).items()]
        for scope, conc in scopes:
            group = conc.get("group") if isinstance(conc, dict) else conc
            if group is not None:
                found.append((path.name, scope, str(group)))
    return found


def test_no_concurrency_group_uses_github_job():
    offenders = [f"{wf}:{scope}: {group}" for wf, scope, group in concurrency_groups() if "github.job" in group]
    assert not offenders, "concurrency.group cannot use github.job:\n" + "\n".join(offenders)


def test_data_pipeline_job_groups_are_unique():
    groups = [g for wf, scope, g in concurrency_groups() if wf == "data-pipeline.yml" and scope != "<workflow>"]
    assert groups
    assert len(groups) == len(set(groups))
