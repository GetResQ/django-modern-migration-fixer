"""
Lightweight Git helpers backed by the git CLI.

No GitPython, supports standard repos and git worktrees by discovering the
repository root via `git rev-parse --show-toplevel`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable

DEFAULT_TIMEOUT = int(os.environ.get("MODERN_MIGRATION_FIXER_GIT_TIMEOUT", "120"))


class GitError(RuntimeError):
    pass


@runtime_checkable
class GitLike(Protocol):
    def run(self, *args: str, **kwargs: object) -> str: ...


@dataclass
class GitEnv:
    cwd: str

    def run(self, *args: str, timeout: int = DEFAULT_TIMEOUT, check: bool = True) -> str:
        cmd = ["git", *args]
        try:
            res = subprocess.run(
                cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
            )
        except FileNotFoundError as e:  # pragma: no cover
            raise GitError("git executable not found") from e

        if check and res.returncode != 0:
            raise GitError(
                f"git command failed ({shlex.join(cmd)}):\n{res.stderr or res.stdout}"
            )
        return (res.stdout or "").strip()


def is_repo(ge: GitLike) -> bool:
    try:
        out = ge.run("rev-parse", "--is-inside-work-tree")
        return out.lower() == "true"
    except GitError:
        return False


def worktree_root(ge: GitLike) -> str:
    return ge.run("rev-parse", "--show-toplevel")


def is_dirty(ge: GitLike) -> bool:
    out = ge.run("status", "--porcelain=v1", check=True)
    return bool(out)


def fetch_branch(ge: GitLike, remote: str, branch: Optional[str] = None, force: bool = False) -> None:
    args: List[str] = ["fetch", remote]
    if branch:
        args.append(branch)
    if force:
        args.insert(1, "--force")
    ge.run(*args)


def rev_parse(ge: GitLike, ref: str) -> Optional[str]:
    try:
        return ge.run("rev-parse", "--verify", "--quiet", ref) or None
    except GitError:
        return None


def diff_names(ge: GitLike, base: str, head: str) -> List[str]:
    """Return a list of changed file paths (relative to repo root)."""
    out = ge.run("diff", "--name-only", base, head)
    return [line for line in out.splitlines() if line]
