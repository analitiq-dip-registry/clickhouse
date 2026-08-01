"""Unit tests for ClickHouseDialect.

Covers build_tls_connect_args to confirm the asynch DBAPI kwarg surface:
`secure` and `verify` are direct named parameters of
asynch.proto.connection.Connection at 0.2.4+ and 0.3.x, so the mapping
here does not silently lose the verification flag.
"""
import pytest

from connector import ClickHouseDialect


@pytest.fixture()
def dialect() -> ClickHouseDialect:
    return ClickHouseDialect()


class TestBuildTlsConnectArgs:
    def test_disable_returns_only_secure_false(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args("disable", None) == {"secure": False}

    def test_require_returns_secure_true_verify_false(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args("require", None) == {
            "secure": True,
            "verify": False,
        }

    def test_verify_full_returns_secure_true_verify_true(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args("verify-full", None) == {
            "secure": True,
            "verify": True,
        }

    def test_none_mode_defaults_to_verify_full(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args(None, None) == {"secure": True, "verify": True}

    def test_empty_string_defaults_to_verify_full(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args("", None) == {"secure": True, "verify": True}

    def test_mode_is_case_insensitive(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args("VERIFY-FULL", None) == {
            "secure": True,
            "verify": True,
        }
        assert dialect.build_tls_connect_args("DISABLE", None) == {"secure": False}
        assert dialect.build_tls_connect_args("Require", None) == {
            "secure": True,
            "verify": False,
        }

    def test_mode_strips_surrounding_whitespace(self, dialect: ClickHouseDialect) -> None:
        assert dialect.build_tls_connect_args("  verify-full  ", None) == {
            "secure": True,
            "verify": True,
        }

    def test_unknown_mode_raises_value_error(self, dialect: ClickHouseDialect) -> None:
        with pytest.raises(ValueError, match="unsupported ssl_mode"):
            dialect.build_tls_connect_args("tls", None)

    def test_ca_pem_raises_value_error(self, dialect: ClickHouseDialect) -> None:
        with pytest.raises(ValueError, match="ca_certs"):
            dialect.build_tls_connect_args(
                "verify-full",
                "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
            )

    def test_ca_pem_raises_even_for_require_mode(self, dialect: ClickHouseDialect) -> None:
        with pytest.raises(ValueError):
            dialect.build_tls_connect_args("require", "some_pem_data")
