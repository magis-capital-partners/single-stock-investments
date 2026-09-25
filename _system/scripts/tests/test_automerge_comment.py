"""automerge_comment.py: one marker comment per PR, never on a closed one."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "automerge_comment.py"
spec = importlib.util.spec_from_file_location("automerge_comment", SCRIPT)
ac = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ac
spec.loader.exec_module(ac)


class FakeGh:
    def __init__(self, state="OPEN", existing=""):
        self.state = state
        self.existing = existing
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["pr", "view"]:
            return self.state + "\n"
        if args[0] == "api" and "--paginate" in args:
            return self.existing
        return "{}"

    def writes(self):
        return [call for call in self.calls if "--method" in call]


def test_a_merged_pr_gets_no_comment():
    """The twin run commented "blocked" on merged #1013, #1018 and #1020."""
    gh = FakeGh(state="MERGED")
    assert ac.upsert("o/r", "1018", ac.render("Automerge is blocked", "x"), gh=gh) == "skipped"
    assert gh.writes() == []


def test_an_existing_marker_comment_is_updated_in_place():
    gh = FakeGh(existing="987654\n")
    body = ac.render("Automerge needs CI re-triggered", "conflicts with main were resolved at abc123.", "https://run")
    assert ac.upsert("o/r", "1021", body, gh=gh) == "updated"
    (write,) = gh.writes()
    assert write[:4] == ["api", "--method", "PATCH", "repos/o/r/issues/comments/987654"]
    assert write[-1] == f"body={body}"


def test_the_first_comment_is_created():
    gh = FakeGh(existing="")
    assert ac.upsert("o/r", "1021", ac.render("Automerge is blocked", "why"), gh=gh) == "created"
    (write,) = gh.writes()
    assert write[:4] == ["api", "--method", "POST", "repos/o/r/issues/1021/comments"]


def test_the_body_carries_the_marker_the_lookup_searches_for():
    body = ac.render("Automerge needs CI re-triggered", "resolved at abc123", "https://run/1")
    assert body.startswith(ac.MARKER + "\n")
    assert "**Automerge needs CI re-triggered**: resolved at abc123" in body
    assert "[Automerge run](https://run/1)." in body
    gh = FakeGh()
    ac.upsert("o/r", "1", body, gh=gh)
    lookup = next(call for call in gh.calls if "--paginate" in call)
    assert ac.MARKER in lookup[-1]
