"""Las pruebas ASGI de api/tests también pertenecen a la suite unitaria de pytest."""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "/api/tests/" in str(item.path):
            item.add_marker(pytest.mark.unit)
