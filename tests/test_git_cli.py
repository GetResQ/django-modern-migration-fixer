from __future__ import annotations

import unittest

from migration_fixer.git_cli import diff_names, is_repo, rev_parse


class Dummy:
    def __init__(self, mapping: dict[tuple[str, ...], str]):
        self.mapping = mapping

    def run(self, *args: str, **_: object) -> str:
        return self.mapping.get(tuple(args), "")


class TestGitCli(unittest.TestCase):
    def test_is_repo_true_false(self):
        assert is_repo(Dummy({("rev-parse", "--is-inside-work-tree"): "true"})) is True
        assert is_repo(Dummy({("rev-parse", "--is-inside-work-tree"): "false"})) is False


    def test_rev_parse_and_diff_names(self):
        ge = Dummy({
            ("rev-parse", "--verify", "--quiet", "HEAD"): "abc123",
            ("diff", "--name-only", "base", "head"): "a.txt\nmigrations/0002_x.py\n\n",
        })
        assert rev_parse(ge, "HEAD") == "abc123"
        assert diff_names(ge, "base", "head") == ["a.txt", "migrations/0002_x.py"]
