"""Unit tests for ClickHouseDialect.

Covers build_tls_connect_args to confirm the asynch DBAPI kwarg surface:
`secure` and `verify` are named parameters on asynch.proto.connection.Connection
at 0.2.4+ and 0.3.x, consumed by name after **kwargs forwarding from the DBAPI
wrapper, so the exact keys the connector passes are the expected proto-layer names.
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

    @pytest.mark.parametrize("mode,expected", [
        ("VERIFY-FULL", {"secure": True, "verify": True}),
        ("DISABLE", {"secure": False}),
        ("Require", {"secure": True, "verify": False}),
    ])
    def test_mode_is_case_insensitive(
        self, dialect: ClickHouseDialect, mode: str, expected: dict
    ) -> None:
        assert dialect.build_tls_connect_args(mode, None) == expected

    @pytest.mark.parametrize("mode", ["  verify-full  ", "  disable  ", "  require  "])
    def test_mode_strips_surrounding_whitespace(
        self, dialect: ClickHouseDialect, mode: str
    ) -> None:
        result = dialect.build_tls_connect_args(mode, None)
        assert "secure" in result

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
        with pytest.raises(ValueError, match="ca_certs"):
            dialect.build_tls_connect_args("require", "some_pem_data")

    def test_empty_string_ca_pem_is_accepted(self, dialect: ClickHouseDialect) -> None:
        # Empty string is falsy; the guard must not raise for it (no CA configured)
        assert dialect.build_tls_connect_args("verify-full", "") == {
            "secure": True,
            "verify": True,
        }

    def test_ca_pem_check_precedes_mode_validation(self, dialect: ClickHouseDialect) -> None:
        # ca_pem guard fires before mode validation; error identifies ca_certs not ssl_mode
        with pytest.raises(ValueError, match="ca_certs"):
            dialect.build_tls_connect_args("not-a-valid-mode", "some_pem_data")
