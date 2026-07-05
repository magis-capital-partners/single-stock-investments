"""Helpers for CI clone/push of magis-capital-partners/research-vault."""
from __future__ import annotations

import re
import urllib.parse

DEFAULT_VAULT_REPO = "magis-capital-partners/research-vault"
DEFAULT_VAULT_URL = f"https://github.com/{DEFAULT_VAULT_REPO}.git"


def normalize_repo_url(raw: str) -> str:
    """Return a credential-free https://github.com/{owner}/{repo}.git URL."""
    url = (raw or "").strip()
    if not url:
        raise ValueError("RESEARCH_VAULT_REPO_URL is empty")

    ssh_match = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", url)
    if ssh_match:
        return f"https://github.com/{ssh_match.group(1)}.git"

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https", ""):
        raise ValueError(f"unsupported URL scheme: {parsed.scheme or '(none)'}")

    host = (parsed.hostname or "github.com").lower()
    if host != "github.com":
        raise ValueError(f"expected github.com host, got {host!r}")

    netloc = host
    path = parsed.path.rstrip("/")
    if not path:
        raise ValueError("repository path missing from RESEARCH_VAULT_REPO_URL")
    if not path.endswith(".git"):
        path = f"{path}.git"

    return urllib.parse.urlunparse(("https", netloc, path, "", "", ""))


def parse_github_repository(raw: str) -> str:
    """Return owner/repo from a clone URL."""
    clean = normalize_repo_url(raw)
    path = urllib.parse.urlparse(clean).path.lstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if path.count("/") != 1:
        raise ValueError(f"expected owner/repo in URL, got {path!r}")
    return path


def vault_auth_hint() -> str:
    return (
        "Verify RESEARCH_VAULT_CLONE_TOKEN is a fine-grained PAT with Contents read "
        f"(and write for backfill) on {DEFAULT_VAULT_REPO}, that the token owner has "
        "org SSO authorized if required, and RESEARCH_VAULT_REPO_URL points at "
        f"{DEFAULT_VAULT_URL}. See _system/reference/research-vault-split.md."
    )
