# django-modern-migration-fixer

Fix conflicting Django migrations (numbered styles) using plain git CLI, with robust support for normal repos and git worktrees. No GitPython dependency.

This is a fork and drop-in replacement for [django-migration-fixer](https://github.com/tj-django/django-migration-fixer) which is not actively maintained by the author.

- Detects conflicting leaf nodes and renumbers local migrations to form a single linear chain.
- Rewrites `dependencies` to point to the last migration on the default branch.
- Works in git worktrees by discovering the repo root via `git rev-parse --show-toplevel`.

## Install

```bash
uv pip install django-modern-migration-fixer
```

Add to your Django settings:

```python
INSTALLED_APPS = [
    # ...
    "django_modern_migration_fixer",
    # ...
]
```

## Usage

```bash
./manage.py makemigrations --fix [apps...]
```

Useful flags:
- `-b, --default-branch`: Name of the default branch (default: `master`).
- `-r, --remote`: Git remote (default: `origin`).
- `-s, --skip-default-branch-update`: Skip fetching remote default branch.
- `-f, --force-update`: Force update the default branch refs before fixing.

Examples:

```bash
./manage.py makemigrations --fix
./manage.py makemigrations --fix -b master --skip-default-branch-update
./manage.py makemigrations --fix -r upstream --force-update
```

## How it works

- On a `Conflicting migrations` error, the command:
  - Verifies the repo is clean.
  - Optionally fetches the default branch.
  - Resolves default-branch and HEAD SHAs robustly.
  - Loads the migration graph and finds conflicts per app.
  - Filters changed migration files under the app’s migration folder between default SHA and HEAD.
  - Renumbers local files and rewrites dependencies to form a single chain.

## Limitations

- Only supports numbered migration file names (e.g., `0001_initial`). Non-numbered names fail fast with a clear message.
- Cross-app dependency rewrites beyond simple renumbering are out of scope.

## Development

```bash
uv sync --extra dev
uv run ruff check --fix . && uv run ruff format .
uv run -m unittest
uv build && uvx twine check dist/*
```

## Make targets

Convenient shortcuts are available via `make`:

- `make tests` — Run unit and e2e tests (unittest discovery).
- `make tests-unit` — Discover and run tests under `tests/unit`.
- `make tests-e2e` — Discover and run tests under `tests/e2e` (safe if empty).
- `make build` — `uv sync --extra dev` then `uv build` to produce wheels/sdist.
- `make distribute` — `twine check` then upload artifacts in `dist/` to PyPI.

Notes:
- Test runs set `PYTHONPATH=src` so the package imports without installation.
- `build` and `distribute` require `uv` to be installed and available on PATH.

## License

MIT
