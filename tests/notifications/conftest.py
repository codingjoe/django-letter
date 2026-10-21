from collections.abc import Iterator

import pytest

from django_letter.notifications import registry


@pytest.fixture(autouse=True)
def restore_registry() -> Iterator[None]:
    """Return the global registry to its import-time state after each test."""
    before = list(registry)
    yield
    registry[:] = before
