import tempfile
import unittest
from pathlib import Path

from django_modern_migration_fixer.utils import (
    fix_numbered_migration,
    get_filename,
    migration_sorter,
)


class TestUtils(unittest.TestCase):
    def test_get_filename_and_sorter(self):
        self.assertEqual(get_filename("/x/y/0002_foo.py"), "0002_foo")
        self.assertEqual(migration_sorter("/x/y/0010_bar.py", app_label="mf"), 10)
        with self.assertRaises(ValueError):
            migration_sorter("/x/y/not_numbered.py", app_label="mf")

    def test_fix_numbered_migration(self):
        with tempfile.TemporaryDirectory() as td:
            mig_dir = Path(td)
            app_label = "mf"
            m2 = mig_dir / "0002_local_a.py"
            m3 = mig_dir / "0003_local_b.py"
            for p in (m2, m3):
                p.write_text(
                    """
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('mf', '0001_initial'),
    ]
    operations = []
                    """.strip()
                )

            logs: list[str] = []
            fix_numbered_migration(
                app_label=app_label,
                migration_path=mig_dir,
                seed=2,
                start_name="0002_seed_from_default",
                changed_files=[str(m2), str(m3)],
                writer=lambda m: logs.append(m),
            )
            self.assertTrue((mig_dir / "0003_local_a.py").exists())
            self.assertTrue((mig_dir / "0004_local_b.py").exists())

