import importlib

import pytest

migration = importlib.import_module(
    "django_letter.notifications.migrations.0001_initial"
)


class Connection:
    def __init__(self, vendor: str) -> None:
        self.vendor = vendor


class SchemaEditor:
    def __init__(self, vendor: str) -> None:
        self.connection = Connection(vendor)
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


@pytest.mark.parametrize(
    ("vendor", "statements"),
    [
        ("postgresql", ["CREATE EXTENSION IF NOT EXISTS pgcrypto"]),
        ("sqlite", []),
    ],
)
def test_create_pgcrypto(vendor: str, statements: list[str]) -> None:
    editor = SchemaEditor(vendor)
    migration.create_pgcrypto(None, editor)
    assert editor.statements == statements
