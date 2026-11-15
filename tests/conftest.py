"""pytest distingue ejecución local de operaciones con servicios reales."""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.integration if "/integration/" in str(item.path) else pytest.mark.unit)
