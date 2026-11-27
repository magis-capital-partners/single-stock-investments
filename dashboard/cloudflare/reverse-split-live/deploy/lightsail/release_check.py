"""Confirm Box R's exact main revision passed the GitHub research deployment."""

import json
import re
import sys
from urllib.request import urlopen


def release_status(commit, get):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Expected a full Git commit SHA")
    path = (
        "/actions/workflows/reverse-split-live.yml/runs"
        f"?branch=main&head_sha={commit}&per_page=30"
    )
    runs = get(path)["workflow_runs"]
    for run in runs:
        if (run["head_sha"] != commit or run["head_branch"] != "main"
                or run["event"] not in {"push", "repository_dispatch"}
                or run["status"] != "completed" or run["conclusion"] != "success"):
            continue
        jobs = get(f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=30")["jobs"]
        if any(job["name"] == "deploy" and job["head_sha"] == commit
               and job["status"] == "completed" and job["conclusion"] == "success"
               for job in jobs):
            return "success"
    return "no successful exact-commit deploy"


def get_github(repo, path):
    with urlopen(f"https://api.github.com/repos/{repo}{path}", timeout=20) as response:
        return json.load(response)


if __name__ == "__main__":
    repository, revision = sys.argv[1:]
    print(release_status(revision, lambda path: get_github(repository, path)))
