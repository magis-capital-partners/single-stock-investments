"""Resolve owned research links without inventing files or accessing a network service."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import quote, unquote, urlsplit

SSI_REPO = "magis-capital-partners/single-stock-investments"
VAULT_REPO = "magis-capital-partners/research-vault"
SSI_REPOS = {SSI_REPO.lower(), "goldmandrew/single-stock-investments"}
VAULT_PREFIXES = (
    ("_system/reference/video/library/", "videos/library/"),
    ("_system/reference/podcasts/episodes/", "podcasts/episodes/"),
    ("_system/reference/superinvestor-letters/", "superinvestor-letters/"),
    ("_system/reference/investment-wisdom/", "investment-wisdom/"),
    ("_system/reference/sumzero-research/", "sumzero-research/"),
    ("_system/reference/vic-research/", "vic-research/"),
    ("_system/reference/manager-meetings/", "manager-meetings/"),
)


@lru_cache(maxsize=8)
def tracked_files(root: str, remote: bool = False) -> frozenset[str]:
    """Tree metadata covers sparse checkouts too. Never fetch missing blobs."""
    if not (Path(root) / ".git").exists():
        return frozenset()
    refs = ["origin/main", "HEAD"] if remote else ["HEAD"]
    for ref in refs:
        result = subprocess.run(["git", "-C", root, "ls-tree", "-r", "--name-only", "-z", ref],
                                capture_output=True, timeout=30)
        if result.returncode == 0:
            return frozenset(result.stdout.decode("utf-8", errors="replace").split("\0")) - {""}
    return frozenset()


def repository_url(ref: str, repo: str = SSI_REPO, *, raw: bool = False, directory: bool = False, anchor: str = "") -> str:
    if repo.lower() in SSI_REPOS:
        repo = SSI_REPO
    encoded = quote(ref.replace("\\", "/").strip("/"), safe="/")
    if raw:
        return f"https://raw.githubusercontent.com/{repo}/main/{encoded}{anchor}"
    return f"https://github.com/{repo}/{'tree' if directory else 'blob'}/main/{encoded}{anchor}"


class SourceLinks:
    def __init__(self, root: Path, vault: Path | None = None):
        self.root = Path(root).resolve()
        self.vault = Path(vault).resolve() if vault else None
        self.counts: Counter = Counter()
        self.repairs: dict[str, dict] = {}
        self._cache: dict[str, str | None] = {}

    def exists(self, ref: str, *, private: bool = False, directory: bool = False) -> bool:
        if not ref or ".." in PurePosixPath(ref).parts or re.match(r"^[A-Za-z]:", ref):
            return False
        root = self.vault if private else self.root
        if root is None:
            return False
        path = root / ref
        if (path.is_dir() if directory else path.is_file()):
            return True
        files = tracked_files(str(root), private)
        return any(name.startswith(ref.rstrip("/") + "/") for name in files) if directory else ref in files

    def ref_url(self, ref: str, *, repo: str = SSI_REPO, raw: bool = False, directory: bool = False, anchor: str = "") -> str | None:
        ref = str(ref).strip().replace("\\", "/").lstrip("/")
        private = repo.lower() == VAULT_REPO.lower()
        if not private:
            for before, after in VAULT_PREFIXES:
                if ref.startswith(before):
                    ref, repo, private = after + ref[len(before):], VAULT_REPO, True
                    break
        # A hash can be part of the actual filename. Prefer that exact file.
        if not self.exists(ref, private=private, directory=directory) and "#" in ref and not ref.lower().endswith((".pdf", ".md", ".txt")):
            ref, fragment = ref.split("#", 1)
            anchor = "#" + fragment
        candidates = [ref]
        if ref.endswith(".pdf.txt"):
            candidates = [ref[:-4], ref]
        elif ref.endswith(".pdf.pdf"):
            candidates += [ref[:-4] + ".txt", ref[:-4], ref[:-8] + ".md"]
        elif ref.endswith(".pdf"):
            candidates += [ref[:-4] + ".md", ref[:-4] + ".txt", ref + ".txt"]
        for candidate in candidates:
            if self.exists(candidate, private=private, directory=directory):
                return repository_url(candidate, repo, raw=raw, directory=directory, anchor=anchor)
        return None

    def resolve(self, value: str | None) -> str | None:
        if not value:
            return None
        if value in self._cache:
            return self._cache[value]
        result = self._resolve(value)
        self._cache[value] = result
        if result != value:
            status = "repaired" if result else "unavailable"
            self.counts[status] += 1
            self.repairs[value] = {"url": result, "status": status}
        return result

    def _resolve(self, value: str) -> str | None:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"}:
            return self.ref_url(value) if not parsed.scheme else None
        host = (parsed.hostname or "").lower()
        parts = parsed.path.strip("/").split("/")
        if host not in {"github.com", "www.github.com", "raw.githubusercontent.com"} or len(parts) < 2:
            return value
        repo = "/".join(parts[:2])
        if repo.lower() not in SSI_REPOS | {VAULT_REPO.lower()}:
            return value
        raw = host == "raw.githubusercontent.com"
        offset = 3 if raw else 4
        if not raw and (len(parts) < 4 or parts[2] not in {"blob", "tree", "raw"}):
            return value.replace("GoldmanDrew/single-stock-investments", SSI_REPO)
        if len(parts) <= offset:
            return value
        branch = parts[2] if raw else parts[3]
        # Dated evidence can intentionally pin an old commit. Don't validate it against today's tree.
        if branch not in {"main", "master"}:
            return value
        ref = unquote("/".join(parts[offset:]))
        anchor = "#" + parsed.fragment if parsed.fragment else ""
        # Legacy filenames containing an unescaped # need the full path reconstructed.
        if parsed.fragment and parsed.fragment.lower().endswith((".pdf", ".txt", ".md")):
            full = ref + "#" + parsed.fragment
            mapped = next((after + full[len(before):] for before, after in VAULT_PREFIXES if full.startswith(before)), full)
            if self.exists(mapped, private=repo.lower() == VAULT_REPO.lower() or mapped != full):
                ref, anchor = full, ""
        return self.ref_url(ref, repo=repo, raw=raw or (not raw and parts[2] == "raw"),
                            directory=not raw and parts[2] == "tree", anchor=anchor)

    def repair_tree(self, value):
        """Repair link fields in a publication copy; source ledgers are never changed."""
        if isinstance(value, list):
            return [self.repair_tree(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if isinstance(item, str) and re.search(r"url|href|link", key, re.I) and item.startswith(("https://github.com/", "https://raw.githubusercontent.com/")):
                result[key] = self.resolve(item)
            else:
                result[key] = self.repair_tree(item)
        if isinstance(result.get("locations"), list):
            locations = result["locations"]
            if locations and not any(location.get("url") for location in locations):
                result["availability"] = "unavailable"
            for location in locations:
                if location.get("url", "") and urlsplit(location["url"]).path.endswith((".md", ".txt")):
                    if str(location.get("label", "")).lower() in {"pdf", "open pdf", "original pdf"}:
                        location["label"] = "Read text"
        return result
