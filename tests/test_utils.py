from __future__ import annotations

from pathlib import Path
import sys
import unittest

from migration_fixer.utils import (
    fix_numbered_migration,
    get_filename,
    get_migration_module_path,
    migration_sorter,
)


class TestUtils(unittest.TestCase):
    def test_get_filename_and_sorter(self):
        assert get_filename("/x/y/0002_foo.py") == "0002_foo"
        assert migration_sorter("/x/y/0010_bar.py", app_label="mf") == 10
        with self.assertRaises(ValueError):
            migration_sorter("/x/y/not_numbered.py", app_label="mf")


    def test_get_migration_module_path_import(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            tmp_path = Path(td)
            pkg = tmp_path / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "a.py").write_text("")
            sys.path.insert(0, str(tmp_path))
            try:
                path = get_migration_module_path("pkg")
            finally:
                sys.path.pop(0)
            assert path == pkg


    def test_fix_numbered_migration_renames_and_rewrites(self):
        from tempfile import TemporaryDirectory
        app_label = "mf_widgets"
        with TemporaryDirectory() as td:
            mig_dir = Path(td)
            # Create two changed local migrations with a placeholder dependency
            m2 = mig_dir / "0002_local_a.py"
            m3 = mig_dir / "0003_local_b.py"
            for p in (m2, m3):
                p.write_text(
                    """
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('mf_widgets', '0001_initial'),
    ]
    operations = []
                    """.strip()
                )

            out: list[str] = []

            def writer(msg: str) -> None:
                out.append(msg)

            fix_numbered_migration(
                app_label=app_label,
                migration_path=mig_dir,
                seed=2,
                start_name="0002_seed_from_default",
                changed_files=[str(m2), str(m3)],
                writer=writer,
            )

            # Files should be renamed to 0003_* and 0004_* respectively
            assert (mig_dir / "0003_local_a.py").exists()
            assert (mig_dir / "0004_local_b.py").exists()
            # And their dependencies should now reference the previous element in the chain
            assert "('mf_widgets', '0002_seed_from_default')" in (mig_dir / "0003_local_a.py").read_text()
            assert "('mf_widgets', '0003_local_a')" in (mig_dir / "0004_local_b.py").read_text()
