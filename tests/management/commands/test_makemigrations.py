"""Tests for `migration_fixer` package (CLI-backed) using Django's test runner.

These tests focus on control flow and messaging rather than reproducing the
entire git integration; end-to-end coverage lives under tests/e2e/.
"""

import os
import tempfile
import unittest
from io import StringIO
from unittest import mock

from django.core.management.base import CommandError
from django.core.management.base import OutputWrapper

from migration_fixer.management.commands.makemigrations import Command


def _run(cmd: Command, **kwargs) -> str:
    out = StringIO()
    # BaseCommand only sets stdout/stderr when invoked via run_from_argv; set manually here
    cmd.stdout = OutputWrapper(out)
    cmd.stderr = OutputWrapper(out)
    # Provide defaults resembling Django's option dict
    kwargs.setdefault("merge", False)
    kwargs.setdefault("fix", False)
    kwargs.setdefault("force_update", False)
    kwargs.setdefault("skip_default_branch_update", True)
    kwargs.setdefault("default_branch", "main")
    kwargs.setdefault("remote", "origin")
    return cmd.handle(**kwargs) or out.getvalue()


class TestMakemigrationsFix(unittest.TestCase):
    def test_invalid_repo_raises_clear_error(self):
        # Force Django parent makemigrations to report a conflict so our --fix path runs.
        from django.core.management.commands import makemigrations as mm

        def raise_conflict(self, *args, **kwargs):
            raise CommandError("Conflicting migrations detected; test harness")

        with mock.patch.object(mm.Command, "handle", raise_conflict), \
            mock.patch("migration_fixer.management.commands.makemigrations.is_repo", return_value=False):
            cwd = os.getcwd()
            with tempfile.TemporaryDirectory() as td:
                os.chdir(td)
                try:
                    cmd = Command()
                    cmd.verbosity = 1
                    with self.assertRaises(CommandError) as exc:
                        _run(cmd, fix=True)
                    self.assertIn("Git repository is not yet setup", str(exc.exception))
                finally:
                    os.chdir(cwd)

    def test_no_conflict_path_returns_parent_output(self):
        # When there is no conflict, our command should defer to Django's output.
        from django.core.management.commands import makemigrations as mm

        def ok(self, *args, **kwargs):
            # Simulate Django printing "No changes detected"
            self.stdout.write("No changes detected")

        with mock.patch.object(mm.Command, "handle", ok):
            cmd = Command()
            out = _run(cmd)
            self.assertEqual(out, "No changes detected\n")
