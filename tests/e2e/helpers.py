import os
import sys
import subprocess
from pathlib import Path
from textwrap import dedent


def project_root_from_tests() -> Path:
    p = Path(__file__).resolve()
    while p != p.parent:
        if (p / "pyproject.toml").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parents[3]


def write_minidjango_project(
    root: Path,
    app_name: str = "mf_widgets",
    project_name: str = "testproj",
    apps: list[str] | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    apps = apps or [app_name]
    # manage.py
    (root / "manage.py").write_text(
        dedent(
            f"""
            #!/usr/bin/env python3
            import os, sys
            if __name__ == "__main__":
                os.environ["DJANGO_SETTINGS_MODULE"] = "{project_name}.settings"
                from django.core.management import execute_from_command_line
                execute_from_command_line(sys.argv)
            """
        ).lstrip()
    )
    (root / project_name).mkdir(parents=True, exist_ok=True)
    (root / project_name / "__init__.py").write_text("")
    (root / project_name / "settings.py").write_text(
        dedent(
            f"""
            SECRET_KEY = "test-secret-key"
            DEBUG = True
            USE_TZ = True
            TIME_ZONE = "UTC"
            INSTALLED_APPS = [
                "django.contrib.contenttypes",
                "django_modern_migration_fixer",
                {', '.join(repr(a) for a in apps)}
            ]
            DATABASES = {{
                "default": {{
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": r"{(root / 'db.sqlite3').as_posix()}",
                }}
            }}
            DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
            """
        ).lstrip()
    )
    # Apps
    for a in apps:
        (root / a).mkdir(parents=True, exist_ok=True)
        (root / a / "__init__.py").write_text("")
        class_name = "WidgetsConfig" if a.endswith("widgets") else "AppConfig"
        (root / a / "apps.py").write_text(
            dedent(
                f"""
                from django.apps import AppConfig as Base

                class {class_name}(Base):
                    name = "{a}"
                """
            ).lstrip()
        )
        (root / a / "migrations").mkdir(parents=True, exist_ok=True)
        (root / a / "migrations" / "__init__.py").write_text("")
        # Initial model per app
        model = "Widget" if a.endswith("widgets") else "Gadget"
        (root / a / "models.py").write_text(
            dedent(
                f"""
                from django.db import models

                class {model}(models.Model):
                    title = models.CharField(max_length=50)
                """
            ).lstrip()
        )


def run(cmd, cwd: Path, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=check,
    )


def python_env_for_subproc(project_root: Path) -> dict:
    env = {}
    existing = os.environ.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{project_root}{os.pathsep}{existing}" if existing else str(project_root)
    return env


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=cwd, check=check)


def git_init_main(cwd: Path) -> None:
    # Initialize git and set identity
    git(cwd, "init").check_returncode()
    # Create main branch (compatible with older git that lacks -b on init)
    git(cwd, "checkout", "-b", "main").check_returncode()
    git(cwd, "config", "user.email", "test@example.com").check_returncode()
    git(cwd, "config", "user.name", "Test User").check_returncode()


def python_bin() -> str:
    """Return the Python interpreter to use for subprojects inside the container.

    Prefer the uv project environment when available to ensure Django is importable.
    """
    uv_env = os.environ.get("UV_PROJECT_ENVIRONMENT", "/opt/venv")
    cand = Path(uv_env) / "bin" / "python"
    return str(cand) if cand.exists() else sys.executable
