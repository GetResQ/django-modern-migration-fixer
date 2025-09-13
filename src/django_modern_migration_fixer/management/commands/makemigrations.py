"""
Create a new Django migration with support for fixing conflicts.
"""

from __future__ import annotations

import os
from functools import partial

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.makemigrations import Command as BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections, router
from django.db.migrations.loader import MigrationLoader

from django_modern_migration_fixer.git_cli import (
    GitError,
    GitEnv,
    diff_names,
    fetch_branch,
    is_dirty,
    is_repo,
    rev_parse,
    worktree_root,
)
from django_modern_migration_fixer.utils import (
    fix_numbered_migration,
    get_filename,
    get_migration_module_path,
    migration_sorter,
    no_translations,
)


class Command(BaseCommand):
    help = "Creates new migration(s) for apps and fix conflicts."
    success_msg = "Successfully fixed migrations."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cwd = os.getcwd()
        self.git = GitEnv(cwd=self.cwd)

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Fix migrations conflicts.")
        parser.add_argument(
            "-b",
            "--default-branch",
            help="The name of the default branch.",
            default="master",
        )
        parser.add_argument(
            "-s",
            "--skip-default-branch-update",
            help="Skip pulling the latest changes from the default branch.",
            action="store_true",
        )
        parser.add_argument(
            "-r",
            "--remote",
            help="Git remote.",
            default="origin",
        )
        parser.add_argument(
            "-f",
            "--force-update",
            help="Force update the default branch.",
            action="store_true",
        )
        super().add_arguments(parser)

    @no_translations
    def handle(self, *app_labels, **options):
        self.merge = options["merge"]
        self.fix = options["fix"]
        self.force_update = options["force_update"]
        self.skip_default_branch_update = options["skip_default_branch_update"]
        self.default_branch = options["default_branch"]
        self.remote = options["remote"]

        if self.fix:
            try:
                super().handle(*app_labels, **options)
            except CommandError as e:
                [message] = e.args
                if "Conflicting migrations" in message:
                    if self.verbosity >= 2:
                        self.stdout.write("Verifying git repository...")

                    if not is_repo(self.git):
                        raise CommandError(
                            self.style.ERROR(
                                f"Git repository is not yet setup. Please run (git init) in\n\"{self.cwd}\""
                            )
                        )

                    if self.verbosity >= 2:
                        self.stdout.write("Retrieving the current branch...")

                    if is_dirty(self.git):  # pragma: no cover
                        raise CommandError(
                            self.style.ERROR(
                                "Git repository has uncommitted changes. Please commit any outstanding changes."
                            )
                        )

                    if not self.skip_default_branch_update:
                        if self.verbosity >= 2:
                            self.stdout.write(
                                f"Fetching git remote {self.remote} changes on: {self.default_branch}"
                            )
                        try:
                            fetch_branch(self.git, self.remote, None, force=self.force_update)
                        except GitError as e:  # pragma: no cover
                            raise CommandError(
                                self.style.ERROR(
                                    f"Unable to fetch {self.remote}/{self.default_branch}: {e}"
                                )
                            )

                    candidates = [
                        f"{self.remote}/{self.default_branch}",
                        f"{self.remote}/HEAD",
                        # Try common default-branch names explicitly as fallbacks
                        f"{self.remote}/main",
                        f"{self.remote}/master",
                        self.default_branch,
                        "main",
                        "master",
                    ]
                    default_sha = None
                    chosen_ref = None
                    for ref in candidates:
                        sha = rev_parse(self.git, ref)
                        if sha:
                            default_sha = sha
                            chosen_ref = ref
                            break
                    if self.verbosity >= 2 and chosen_ref:
                        self.stdout.write(
                            f"Retrieving the last commit sha on: {chosen_ref}"
                        )
                    if not default_sha:
                        raise CommandError(
                            self.style.ERROR(
                                f"Unable to resolve default branch ref. Tried: {', '.join(candidates)}"
                            )
                        )
                    current_sha = rev_parse(self.git, "HEAD")
                    if not current_sha:
                        raise CommandError(self.style.ERROR("Unable to resolve HEAD"))

                    if self.verbosity >= 2:
                        self.stdout.write(
                            f"Retrieving the last commit sha on: {self.default_branch}"
                        )

                    loader = MigrationLoader(None, ignore_no_migrations=True)

                    consistency_check_labels = {config.label for config in apps.get_app_configs()}
                    aliases_to_check = (
                        connections if settings.DATABASE_ROUTERS else [DEFAULT_DB_ALIAS]
                    )
                    for alias in sorted(aliases_to_check):
                        connection = connections[alias]
                        if connection.settings_dict["ENGINE"] != "django.db.backends.dummy" and any(
                            router.allow_migrate(
                                connection.alias,
                                app_label,
                                model_name=model._meta.object_name,
                            )
                            for app_label in consistency_check_labels
                            for model in apps.get_app_config(app_label).get_models()
                        ):
                            loader.check_consistent_history(connection)

                    conflict_leaf_nodes = loader.detect_conflicts()

                    for app_label, leaf_nodes in conflict_leaf_nodes.items():
                        migration_module, _ = loader.migrations_module(app_label)
                        migration_path = get_migration_module_path(migration_module)

                        if self.verbosity >= 2:
                            self.stdout.write(
                                "Retrieving changed files between the current branch and "
                                f"{self.default_branch}"
                            )

                        try:
                            repo_root = worktree_root(self.git)
                            rel_changed = diff_names(self.git, default_sha, current_sha)
                            changed_files = []
                            for rel in rel_changed:
                                abs_path = os.path.join(repo_root, rel)
                                if str(abs_path).startswith(str(migration_path)):
                                    changed_files.append(abs_path)

                            sorted_changed_files = sorted(
                                changed_files, key=partial(migration_sorter, app_label=app_label)
                            )

                            local_filenames = [get_filename(p) for p in sorted_changed_files]

                            conflict_bases = [name for name in leaf_nodes if name not in local_filenames]
                            if not conflict_bases:  # pragma: no cover
                                raise CommandError(
                                    self.style.ERROR(
                                        f"Unable to determine the last migration on: {self.default_branch}. "
                                        "Please verify the target branch using\n\"-b [target branch]\".",
                                    )
                                )

                            conflict_base = conflict_bases[0]

                            if self.verbosity >= 2:
                                self.stdout.write(
                                    f"Retrieving the last migration on: {self.default_branch}"
                                )

                            seed_split = conflict_base.split("_")
                            if seed_split and len(seed_split) > 1 and str(seed_split[0]).isdigit():
                                if self.verbosity >= 2:
                                    self.stdout.write("Fixing numbered migration...")

                                fix_numbered_migration(
                                    app_label=app_label,
                                    migration_path=migration_path,
                                    seed=int(seed_split[0]),
                                    start_name=conflict_base,
                                    changed_files=sorted_changed_files,
                                    writer=(
                                        lambda m: (
                                            self.stdout.write(m) if self.verbosity >= 2 else None
                                        )
                                    ),
                                )
                            else:  # pragma: no cover
                                raise ValueError(
                                    f"Unable to fix migration: {conflict_base}. \n"
                                    f"NOTE: It needs to begin with a number. eg. 0001_*",
                                )
                        except (ValueError, IndexError, TypeError) as e:
                            self.stderr.write(f"Error: {e}")
                        else:
                            self.stdout.write(self.success_msg)
        else:
            return super(Command, self).handle(*app_labels, **options)
