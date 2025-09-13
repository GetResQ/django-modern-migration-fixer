from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from .helpers import (
    git,
    run,
    project_root_from_tests,
    python_bin,
    python_env_for_subproc,
    write_minidjango_project,
)


def write_manual_migration(app_dir: Path, name: str, dep: str = "0001_initial") -> None:
    (app_dir / "migrations" / f"{name}.py").write_text(
        f"""
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("{app_dir.name}", "{dep}"),
    ]
    operations = []
        """.strip()
    )


class TestE2EExtended(unittest.TestCase):
    def test_fix_conflicts_multiple_local_chain_branch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_minidjango_project(root)
            (root / ".gitignore").write_text("__pycache__/\n*.pyc\ndb.sqlite3\n")

            # init repo on main
            git(root, "init")
            git(root, "checkout", "-b", "main")
            git(root, "config", "user.email", "test@example.com")
            git(root, "config", "user.name", "Test User")

            env = python_env_for_subproc(project_root_from_tests())

            # initial
            run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "-n", "initial"], cwd=root, env=env)
            git(root, "add", ".")
            git(root, "commit", "-m", "0001")

            git(root, "branch", "feature/a")

            # main gets 0002_main
            write_manual_migration(root / "mf_widgets", "0002_main")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 main")

            # feature gets two locals 0002_local_a + 0003_local_b
            git(root, "checkout", "feature/a")
            write_manual_migration(root / "mf_widgets", "0002_local_a")
            write_manual_migration(root / "mf_widgets", "0003_local_b")
            git(root, "add", ".")
            git(root, "commit", "-m", "local chain a+b")

            # merge
            git(root, "merge", "--no-edit", "main")

            # fix
            res = run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "--fix", "--skip-default-branch-update"], cwd=root, env=env)
            self.assertIn("Successfully fixed migrations", (res.stdout + res.stderr))

            migs = sorted((root / "mf_widgets" / "migrations").glob("0*.py"))
            names = [p.stem for p in migs]
            self.assertTrue(any(n == "0003_local_a" for n in names), names)
            self.assertTrue(any(n == "0004_local_b" for n in names), names)

            # dependencies updated
            m3 = root / "mf_widgets" / "migrations" / "0003_local_a.py"
            m4 = root / "mf_widgets" / "migrations" / "0004_local_b.py"
            t3 = m3.read_text()
            t4 = m4.read_text()
            self.assertTrue(("('mf_widgets', '0002_main')" in t3) or ('("mf_widgets", "0002_main")' in t3))
            self.assertTrue(("('mf_widgets', '0003_local_a')" in t4) or ('("mf_widgets", "0003_local_a")' in t4))

            # migrate
            mig = run([python_bin(), "manage.py", "migrate", "--noinput"], cwd=root, env=env)
            self.assertEqual(mig.returncode, 0)

    def test_fix_conflicts_multi_app_branch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_minidjango_project(root, apps=["mf_widgets", "mf_gadgets"])
            (root / ".gitignore").write_text("__pycache__/\n*.pyc\ndb.sqlite3\n")

            git(root, "init")
            git(root, "checkout", "-b", "main")
            git(root, "config", "user.email", "test@example.com")
            git(root, "config", "user.name", "Test User")

            env = python_env_for_subproc(project_root_from_tests())

            # initial for both apps
            run([python_bin(), "manage.py", "makemigrations", "-n", "initial"], cwd=root, env=env)
            git(root, "add", ".")
            git(root, "commit", "-m", "0001 both apps")
            git(root, "branch", "feature/a")

            # main 0002 for both apps
            write_manual_migration(root / "mf_widgets", "0002_main")
            write_manual_migration(root / "mf_gadgets", "0002_main")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 main both")

            # feature 0002 for both apps
            git(root, "checkout", "feature/a")
            write_manual_migration(root / "mf_widgets", "0002_feature")
            write_manual_migration(root / "mf_gadgets", "0002_feature")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 feature both")

            git(root, "merge", "--no-edit", "main")

            res = run([python_bin(), "manage.py", "makemigrations", "--fix", "--skip-default-branch-update"], cwd=root, env=env)
            self.assertIn("Successfully fixed migrations", (res.stdout + res.stderr))

            # widgets
            m3w = next((root / "mf_widgets" / "migrations").glob("0003_*.py"))
            wtxt = m3w.read_text()
            self.assertTrue(("('mf_widgets', '0002_main')" in wtxt) or ('("mf_widgets", "0002_main")' in wtxt))
            # gadgets
            m3g = next((root / "mf_gadgets" / "migrations").glob("0003_*.py"))
            gtxt = m3g.read_text()
            self.assertTrue(("('mf_gadgets', '0002_main')" in gtxt) or ('("mf_gadgets", "0002_main")' in gtxt))

            mig = run([python_bin(), "manage.py", "migrate", "--noinput"], cwd=root, env=env)
            self.assertEqual(mig.returncode, 0)

    def test_fix_conflicts_master_default_branch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_minidjango_project(root)
            (root / ".gitignore").write_text("__pycache__/\n*.pyc\ndb.sqlite3\n")

            # Init repo on master (no remotes)
            git(root, "init")
            # Some git installations default to master already; ensure it
            git(root, "checkout", "-B", "master")
            git(root, "config", "user.email", "test@example.com")
            git(root, "config", "user.name", "Test User")

            env = python_env_for_subproc(project_root_from_tests())

            run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "-n", "initial"], cwd=root, env=env)
            git(root, "add", ".")
            git(root, "commit", "-m", "0001")
            git(root, "branch", "feature/a")

            # master 0002
            write_manual_migration(root / "mf_widgets", "0002_from_master")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 master")

            # feature 0002
            git(root, "checkout", "feature/a")
            write_manual_migration(root / "mf_widgets", "0002_from_feature")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 feature")

            git(root, "merge", "--no-edit", "master")

            # Fix, explicitly telling default branch is master; skip fetch
            res = run(
                [
                    python_bin(),
                    "manage.py",
                    "makemigrations",
                    "mf_widgets",
                    "--fix",
                    "--skip-default-branch-update",
                    "-b",
                    "master",
                ],
                cwd=root,
                env=env,
            )
            self.assertIn("Successfully fixed migrations", (res.stdout + res.stderr))

            m3 = next((root / "mf_widgets" / "migrations").glob("0003_*.py"))
            t3 = m3.read_text()
            self.assertTrue(("('mf_widgets', '0002_from_master')" in t3) or ('("mf_widgets", "0002_from_master")' in t3))

            mig = run([python_bin(), "manage.py", "migrate", "--noinput"], cwd=root, env=env)
            self.assertEqual(mig.returncode, 0)

    def test_fix_conflicts_multi_app_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "src"
            wt = tmp / "wt"
            write_minidjango_project(src, apps=["mf_widgets", "mf_gadgets"])
            (src / ".gitignore").write_text("__pycache__/\n*.pyc\ndb.sqlite3\n")

            # Init main repo and initial migrations
            git(src, "init")
            git(src, "checkout", "-b", "main")
            git(src, "config", "user.email", "test@example.com")
            git(src, "config", "user.name", "Test User")

            env = python_env_for_subproc(project_root_from_tests())

            run([python_bin(), "manage.py", "makemigrations", "-n", "initial"], cwd=src, env=env)
            git(src, "add", ".")
            git(src, "commit", "-m", "0001 both apps")

            # 0002 on main for both apps
            write_manual_migration(src / "mf_widgets", "0002_main")
            write_manual_migration(src / "mf_gadgets", "0002_main")
            git(src, "add", ".")
            git(src, "commit", "-m", "0002 main both")

            # Worktree for feature branch
            git(src, "worktree", "add", "-b", "feature/a", str(wt), "main")

            # 0002 on feature for both apps
            write_manual_migration(wt / "mf_widgets", "0002_feature")
            write_manual_migration(wt / "mf_gadgets", "0002_feature")
            git(wt, "add", ".")
            git(wt, "commit", "-m", "0002 feature both")

            # Merge main into worktree branch
            git(wt, "merge", "--no-edit", "main")

            # Fix in worktree
            res = run([python_bin(), "manage.py", "makemigrations", "--fix", "--skip-default-branch-update"], cwd=wt, env=env)
            self.assertIn("Successfully fixed migrations", (res.stdout + res.stderr))

            w3 = next((wt / "mf_widgets" / "migrations").glob("0003_*.py"))
            g3 = next((wt / "mf_gadgets" / "migrations").glob("0003_*.py"))
            self.assertTrue(("('mf_widgets', '0002_main')" in w3.read_text()) or ('("mf_widgets", "0002_main")' in w3.read_text()))
            self.assertTrue(("('mf_gadgets', '0002_main')" in g3.read_text()) or ('("mf_gadgets", "0002_main")' in g3.read_text()))

            mig = run([python_bin(), "manage.py", "migrate", "--noinput"], cwd=wt, env=env)
            self.assertEqual(mig.returncode, 0)

    def test_fix_conflicts_remote_force_update_fetches(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            remote = td / "remote.git"
            pub = td / "pub"
            src = td / "src"
            # Create bare remote
            run(["git", "init", "--bare", str(remote)], cwd=td)

            # Publisher clone to push main history
            run(["git", "clone", str(remote), str(pub)], cwd=td)
            write_minidjango_project(pub)
            (pub / ".gitignore").write_text("__pycache__/\n*.pyc\ndb.sqlite3\n")
            env = python_env_for_subproc(project_root_from_tests())
            run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "-n", "initial"], cwd=pub, env=env)
            git(pub, "-C", str(pub), "checkout", "-b", "main")
            git(pub, "-C", str(pub), "config", "user.email", "test@example.com")
            git(pub, "-C", str(pub), "config", "user.name", "Test User")
            git(pub, "-C", str(pub), "add", ".")
            git(pub, "-C", str(pub), "commit", "-m", "0001")
            git(pub, "-C", str(pub), "push", "-u", "origin", "main")
            # Add 0002 on main and push
            write_manual_migration(pub / "mf_widgets", "0002_from_main")
            git(pub, "-C", str(pub), "add", ".")
            git(pub, "-C", str(pub), "commit", "-m", "0002 main")
            git(pub, "-C", str(pub), "push")

            # Feature clone
            run(["git", "clone", str(remote), str(src)], cwd=td)
            git(src, "-C", str(src), "checkout", "-b", "feature/a", "origin/main")
            # Add conflicting 0002 in feature
            write_manual_migration(src / "mf_widgets", "0002_from_feature")
            git(src, "-C", str(src), "add", ".")
            git(src, "-C", str(src), "config", "user.email", "test@example.com")
            git(src, "-C", str(src), "config", "user.name", "Test User")
            git(src, "-C", str(src), "commit", "-m", "0002 feature")
            # Merge origin/main to create conflict state in working tree
            git(src, "-C", str(src), "merge", "--no-edit", "origin/main")
            # Record current origin/main sha (stale before force fetch)
            before = run(["git", "-C", str(src), "rev-parse", "origin/main"], cwd=src).stdout.strip()

            # Advance remote main again
            write_manual_migration(pub / "mf_widgets", "0003_from_main")
            git(pub, "-C", str(pub), "add", ".")
            git(pub, "-C", str(pub), "commit", "-m", "0003 main")
            git(pub, "-C", str(pub), "push")

            # Run fixer with --force-update to fetch remote updates
            res = run([
                python_bin(),
                "manage.py",
                "makemigrations",
                "mf_widgets",
                "--fix",
                "--force-update",
            ], cwd=src, env=env)
            self.assertIn("Successfully fixed migrations", (res.stdout + res.stderr))

            after = run(["git", "-C", str(src), "rev-parse", "origin/main"], cwd=src).stdout.strip()
            self.assertNotEqual(before, after)

    def test_fix_conflicts_dirty_repo_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_minidjango_project(root)
            (root / ".gitignore").write_text("__pycache__/\n*.pyc\ndb.sqlite3\n")

            git(root, "init")
            git(root, "checkout", "-b", "main")
            git(root, "config", "user.email", "test@example.com")
            git(root, "config", "user.name", "Test User")

            env = python_env_for_subproc(project_root_from_tests())

            run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "-n", "initial"], cwd=root, env=env)
            git(root, "add", ".")
            git(root, "commit", "-m", "0001")
            git(root, "branch", "feature/a")

            write_manual_migration(root / "mf_widgets", "0002_main")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 main")

            git(root, "checkout", "feature/a")
            write_manual_migration(root / "mf_widgets", "0002_feature")
            git(root, "add", ".")
            git(root, "commit", "-m", "0002 feature")
            git(root, "merge", "--no-edit", "main")

            # make repo dirty
            (root / "UNTRACKED.tmp").write_text("dirty")

            res = run([python_bin(), "manage.py", "makemigrations", "mf_widgets", "--fix", "--skip-default-branch-update"], cwd=root, env=env, check=False)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Git repository has uncommitted changes", (res.stdout + res.stderr))
