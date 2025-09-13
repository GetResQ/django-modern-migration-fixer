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


class TestE2EWorktree(unittest.TestCase):
    def test_fix_conflicts_single_app_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            # Create base repo under src/
            src = tmp_path / "src"
            src.mkdir(parents=True)

            # Build the mini project into src and init git
            write_minidjango_project(src)
            # Keep repo clean: ignore pyc, __pycache__, sqlite
            (src / ".gitignore").write_text("""\n__pycache__/\n*.pyc\ndb.sqlite3\n""".lstrip())
            env = python_env_for_subproc(project_root_from_tests())
            git_init_main(src)

            # Initial migration (0001)
            run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "-n", "initial"], cwd=src, env=env)
            git(src, "add", ".")
            git(src, "commit", "-m", "feat(mf_widgets): 0001 initial")

            # On main: create a manual migration only (avoid model merge conflicts)
            (src / "mf_widgets" / "migrations" / "0002_from_main.py").write_text(
                """
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("mf_widgets", "0001_initial"),
    ]
    operations = []
                """.strip()
            )
            git(src, "add", ".")
            git(src, "commit", "-m", "0002 main (manual)")

            # Create worktree at wt/ for feature/a
            wt = tmp_path / "wt"
            git(src, "worktree", "add", "-b", "feature/a", str(wt), "main")

            # In worktree, add a different manual migration → 0002 on feature
            (wt / "mf_widgets" / "migrations" / "0002_from_feature.py").write_text(
                """
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("mf_widgets", "0001_initial"),
    ]
    operations = []
                """.strip()
            )
            git(wt, "add", ".")
            git(wt, "commit", "-m", "0002 feature (manual)")

            # Merge main into worktree branch to produce the divergent leaf nodes
            git(wt, "merge", "--no-edit", "main")

            # Run the fixer in the worktree (skip fetch)
            fix = run(
                [
                    python_bin(),
                    "manage.py",
                    "makemigrations",
                    "mf_widgets",
                    "--fix",
                    "--skip-default-branch-update",
                ],
                cwd=wt,
                env=env,
            )
            assert "Successfully fixed migrations" in (fix.stdout + fix.stderr)

            migs = sorted((wt / "mf_widgets" / "migrations").glob("0*.py"))
            names = [p.stem for p in migs]
            assert any(n.startswith("0003_") for n in names), names

            # Check dependency rewrite
            m3 = next(p for p in migs if p.stem.startswith("0003_"))
            txt = m3.read_text()
            assert ("('mf_widgets', '0002_from_main')" in txt) or (
                "(\"mf_widgets\", \"0002_from_main\")" in txt
            )

            # Migrate from a fresh DB for the worktree checkout
            mig = run([python_bin(), "manage.py", "migrate", "--noinput"], cwd=wt, env=env)
            assert mig.returncode == 0
