import pytest
from pathlib import Path

from .helpers import (
    project_root_from_tests,
    python_env_for_subproc,
    write_minidjango_project,
)


@pytest.fixture()
def project_root_path() -> Path:
    return project_root_from_tests()


@pytest.fixture()
def make_miniproject(tmp_path: Path, project_root_path: Path):
    def _make() -> tuple[Path, dict]:
        write_minidjango_project(tmp_path)
        env = python_env_for_subproc(project_root_path)
        return tmp_path, env

    return _make
