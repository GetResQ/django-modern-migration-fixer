import pytest


@pytest.fixture(autouse=True)
def use_demo_app(settings):
    settings.INSTALLED_APPS = [
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "migration_fixer",
    ]
