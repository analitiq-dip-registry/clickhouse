"""Pytest configuration: stub out CDK engine modules before collection.

The CDK is provided by the engine image at runtime and is never installed
locally. This conftest is in tests/ (no __init__.py) so pytest loads it as
a standalone module before any test file triggers the root package import.
"""
import sys
from unittest.mock import MagicMock

for _mod in ("cdk", "cdk.sql", "cdk.sql.dialects", "cdk.sql.generic"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_dialects = sys.modules["cdk.sql.dialects"]
if isinstance(_dialects, MagicMock):
    _dialects.SqlDialect = type("SqlDialect", (), {"name": ""})
    _dialects.TableAddress = str

_generic = sys.modules["cdk.sql.generic"]
if isinstance(_generic, MagicMock):
    _generic.GenericSQLConnector = type("GenericSQLConnector", (), {})
