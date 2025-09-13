from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from .helpers import (
    git,
    git_init_main,
    project_root_from_tests,
    python_env_for_subproc,
    python_bin,
    run,
    write_minidjango_project,
)


def write_models(path: Path, lines: list[str]) -> None:
    content = ["from django.db import models\n\n", "class Widget(models.Model):\n", *lines]
    (path / "mf_widgets" / "models.py").write_text("".join(content))

class TestE2EBranch(unittest.TestCase):
    def test_fix_conflicts_single_app_branch(self):
        # Create a minimal Django project in a fresh git repo
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_minidjango_project(root)
            # Ensure repo stays clean: ignore pyc, __pycache__, sqlite
            (root / ".gitignore").write_text("""\n__pycache__/\n*.pyc\ndb.sqlite3\n""".lstrip())
            env = python_env_for_subproc(project_root_from_tests())
            git_init_main(root)

            # Initial migration (0001)
            run(
                [python_bin(), "manage.py", "makemigrations", "mf_widgets", "-n", "initial"],
                cwd=root,
                env=env,
            )
            git(root, "add", ".")
            git(root, "commit", "-m", "feat(mf_widgets): 0001 initial")

            # Branch from 0001
            git(root, "branch", "feature/a")

            # On main: add a fake migration file only (avoids model merge conflicts)
            (root / "mf_widgets" / "migrations" / "0002_from_main.py").write_text(
                """
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("mf_widgets", "0001_initial"),
    ]
    operations = []
                """.strip()
            )
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 main (manual)")

            # Switch to feature branch and diverge → 0002_add_note_feature
            git(root, "checkout", "feature/a")
            # On feature: add a different fake migration file
            (root / "mf_widgets" / "migrations" / "0002_from_feature.py").write_text(
                """
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("mf_widgets", "0001_initial"),
    ]
    operations = []
                """.strip()
            )
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 feature (manual)")

            # Merge main into feature to create two leaf nodes
            git(root, "merge", "--no-edit", "main")

            # Now fix conflicts (skip fetch)
            fix = run(
                [
                    python_bin(),
                    "manage.py",
                    "makemigrations",
                    "mf_widgets",
                    "--fix",
                    "--skip-default-branch-update",
                ],
                cwd=root,
                env=env,
            )
            self.assertIn("Successfully fixed migrations", (fix.stdout + fix.stderr))

            migs = sorted((root / "mf_widgets" / "migrations").glob("0*.py"))
            names = [p.stem for p in migs]
            # Expect a renumbered local migration 0003_*
            self.assertTrue(any(n.startswith("0003_") for n in names), names)

            # 0003 should depend on the 0002 from main
            m3 = next(p for p in migs if p.stem.startswith("0003_"))
            txt = m3.read_text()
            self.assertTrue(
                ("('mf_widgets', '0002_from_main')" in txt)
                or ("(\"mf_widgets\", \"0002_from_main\")" in txt)
            )

            # Graph is conflict-free and no new changes
            out = run(
                [python_bin(), "manage.py", "makemigrations", "mf_widgets"],
                cwd=root,
                env=env,
            )
            self.assertIn("No changes detected", (out.stdout + out.stderr))

            # Fresh migrate succeeds
            mig = run(
                [python_bin(), "manage.py", "migrate", "--noinput"],
                cwd=root,
                env=env,
            )
            self.assertEqual(mig.returncode, 0)
