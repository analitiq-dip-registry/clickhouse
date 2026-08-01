"""ClickHouse connector - dialect + connector class for the Analitiq CDK.

Everything ClickHouse-specific lives here: backtick quoting, the
stage-then-apply write hooks (``CREATE TABLE ... AS <target> ENGINE =
MergeTree ORDER BY tuple()`` for the stage, ``TRUNCATE TABLE`` for the
truncate-insert reset) and the ``asynch`` two-switch TLS surface. Column
types for the write direction are governed entirely by
``definition/type-map-write.json``; this module ships no Python
type-rendering table.

Transport: async SQLAlchemy ``clickhouse+asynch`` - the
``clickhouse-sqlalchemy`` dialect driving the ``asynch`` native-protocol
DBAPI. ClickHouse has no first-class ADBC driver and no Arrow Flight SQL
endpoint, so the decision order stops at the SQLAlchemy tier.

Three write-path facts are declared the way ClickHouse actually behaves,
not the way that would be convenient. The first and third are
declarations with *no* hook behind them on purpose: the CDK's
declaration-consistency rule is that a hook override no declaration
routes a call to is dead code that reads as capability, so where the
declaration already closes the path, this module states the reason and
implements nothing.

* **No upsert grammar.** ClickHouse has no ``MERGE``, no ``ON CONFLICT``
  and no ``ON DUPLICATE KEY``. Row collapsing is a *table engine*
  property (``ReplacingMergeTree`` plus ``FINAL`` / ``OPTIMIZE``), it is
  eventual, and it cannot be expressed as the single statement the CDK's
  ``merge_statement_sql`` hook returns. ``sql_capabilities.merge_form``
  is therefore ``none``, which makes the engine refuse every upsert
  stream at ``configure_schema`` time, before any DDL runs. The two
  constructs that look like substitutes are not: a plain
  ``INSERT INTO <target> SELECT ... FROM <stage>`` duplicates every
  matched row on an ordinary MergeTree target (ClickHouse enforces no
  primary-key uniqueness), and the ``ReplacingMergeTree`` collapse that
  *would* deduplicate depends on how the target table was created and is
  only eventual. Rendering either would turn a declared-unsupported mode
  into silent data corruption, so nothing is rendered - and because the
  handshake gate already refuses first, a dialect-level refusal would be
  unreachable code.
* **No transactional DDL.** ClickHouse commits DDL immediately, so the
  stage is a *real* table (``sql_capabilities.stage.scope: real``)
  created and dropped outside any transaction; the engine's per-batch
  pre-flight ``DROP TABLE IF EXISTS`` is what makes a leaked stage
  self-healing.
* **No dialect-level bulk mechanism.** ClickHouse's fast path *is* the
  native columnar block insert the driver performs for an executemany
  ``INSERT``; it is not ``COPY FROM``, ``LOAD DATA LOCAL INFILE`` or a
  load job, which are the only mechanisms the capability vocabulary can
  name. ``sql_capabilities.bulk_load`` is therefore an empty object -
  the contract's documented spelling of "lands via executemany" - and
  the CDK calls ``bulk_land`` only for a declared mechanism, so this
  dialect implements none. What makes the path fast is batch *size*,
  which the connector asks for through ``write_unit`` (small, frequent
  inserts are what ClickHouse punishes with part explosion).

Two write-path gaps are known and are *not* worked around here, because
neither has a sanctioned dialect-level fix - both need an engine-side
answer and are tracked separately:

* **Target tables must pre-exist.** ClickHouse's ``CREATE TABLE``
  requires an ``ENGINE`` clause. :meth:`ClickHouseDialect.stage_table_sql`
  supplies one for the stage, but the *target* table's ``CREATE`` is
  rendered by the CDK (``cdk.sql.ddl.build_create_table_sql``), which
  emits no table options and exposes no hook for them, so auto-creating a
  destination table fails with "Engine must be specified".
* **Nullable source columns.** ClickHouse columns are ``NOT NULL`` by
  default - the inverse of ANSI - and a nullable column has to be spelled
  ``Nullable(T)``. ``definition/type-map-write.json`` emits bare natives,
  and nullability is applied by the CDK renderer (which omits ``NOT
  NULL`` for a nullable column rather than adding a marker), so
  CDK-rendered target DDL declares every column non-nullable and rejects
  NULLs arriving from a nullable source column.

Registered under connector_id ``clickhouse`` via the package entry points
(``analitiq.source_connectors`` / ``analitiq.destination_connectors``).
"""

from __future__ import annotations

from typing import Any

from cdk.sql.dialects import SqlDialect, TableAddress
from cdk.sql.generic import GenericSQLConnector

#: The connector's declared ssl_mode enum, in declaration order, for error
#: messages.
_ALL_MODES = ("disable", "require", "verify-full")

#: Mode used when a stored connection carries no ssl_mode at all. The
#: connection input declares ``verify-full`` as its default, so an empty
#: value only reaches the dialect from a hand-made connection - and
#: resolving that to the strictest mode fails loudly on a plaintext
#: listener instead of silently connecting in cleartext.
_DEFAULT_MODE = "verify-full"


class ClickHouseDialect(SqlDialect):
    """ClickHouse SQL strategy: backtick quoting, MergeTree stages, no upsert."""

    name = "clickhouse"

    #: ClickHouse accepts both backticks and double quotes for identifiers;
    #: backticks are unambiguous under every ``*_double_quoted_*`` server
    #: setting, so they are what this dialect emits.
    quote_char = "`"

    #: ClickHouse ships the ``system`` database plus the two spellings of
    #: the SQL-standard metadata database, which exist as separate database
    #: entries. All three are hidden from discovery (mirrored in
    #: ``resource_discovery.options.exclude_schemas``).
    system_schemas = ("system", "information_schema", "INFORMATION_SCHEMA")

    #: ClickHouse documents no identifier-length constant; a table name
    #: becomes an escaped on-disk directory name, so the real ceiling is
    #: filesystem-derived and version-dependent. 127 is a conservative
    #: *declared budget*, not a claim about the server. Declared here and as
    #: sql_capabilities.limits.max_identifier_len; the two channels must
    #: agree, because the CDK composes generated stage names within the
    #: declared budget while the conformance kit asserts the composed name
    #: against this class attribute.
    max_identifier_length = 127

    # ---- stage-then-apply write path ---------------------------------------
    def stage_table_sql(
        self, stage: TableAddress, target: TableAddress, *, temp: bool
    ) -> str:
        """``CREATE`` the batch's stage table shaped like *target*.

        ``CREATE TABLE ... AS <other>`` is ClickHouse's documented
        column-copy form: it clones the structure and, by default, the
        source table's engine. Defaulting the engine is exactly what must
        not happen here - cloning a ``ReplicatedMergeTree`` target would
        copy its ZooKeeper path and collide with the table it was cloned
        from, and cloning a ``Distributed`` target would make every staged
        row fan out to the cluster before the engine has applied
        anything. The explicit ``ENGINE = MergeTree ORDER BY tuple()``
        override severs both: a plain local MergeTree with no sorting key
        (``tuple()`` is ClickHouse's documented "no sorting key" spelling,
        and it also sidesteps the nullable-key restriction, since the
        landed columns are not known at render time).

        The connector declares ``sql_capabilities.stage.scope: real``, so
        the engine derives *temp* as False and this always renders a plain
        ``CREATE TABLE``. ClickHouse's ``TEMPORARY`` tables were not
        chosen: they are Memory-engine only, so the whole batch would sit
        in server RAM, and they are session-scoped in a way that does not
        survive a pooled connection being recycled mid-cycle. A real stage
        cannot leak either - the engine pre-flight-``DROP``s each batch's
        stage before creating it, and drops it again when the cycle ends.
        """
        return (
            f"CREATE TABLE {self.quote_table(stage)} AS {self.quote_table(target)} "
            f"ENGINE = MergeTree ORDER BY tuple()"
        )

    # No ``merge_statement_sql``: ClickHouse has no MERGE, ON CONFLICT or
    # ON DUPLICATE KEY grammar, the connector declares
    # ``sql_capabilities.merge_form: none``, and the engine refuses upsert
    # streams at configure_schema before the hook could be reached. An
    # override here would be unreachable code that reads as capability -
    # the module docstring carries the full reasoning.

    def empty_table_sql(self, target: TableAddress) -> str:
        """Empty *target* before a truncate-insert's first batch.

        The ANSI base renders a bare ``DELETE FROM t``, which ClickHouse
        rejects: its ``DELETE FROM`` is a lightweight *mutation* and the
        grammar requires a ``WHERE``. ``TRUNCATE TABLE`` is ClickHouse's
        own empty-all statement, and it is the right one here for a second
        reason - a ``DELETE FROM t WHERE 1`` would only mark rows deleted
        and schedule a mutation, leaving the reset's completion
        asynchronous with respect to the append that follows it.
        ``TRUNCATE``'s implicit commit costs nothing, because the
        connector already declares ``stage.transactional_ddl: false``:
        there is no enclosing transaction for it to break.
        """
        return f"TRUNCATE TABLE {self.quote_table(target)}"

    # No ``bulk_land``: the three mechanisms the capability vocabulary can
    # name (``copy_from``, ``load_data_local_infile``, ``load_job``) are
    # all absent from ClickHouse, so the connector declares an empty
    # ``sql_capabilities.bulk_load`` and the CDK never routes a call to the
    # hook. Batches land through the backend's executemany ``INSERT``,
    # which for ``clickhouse+asynch`` is already ClickHouse's native
    # columnar block insert - there is nothing for a dialect override to
    # add, and declining the fast path is exactly what the base does.

    # ---- TLS ------------------------------------------------------------------
    def build_tls_connect_args(self, mode: str, ca_pem: str | None) -> dict[str, Any]:
        """Interpret the declared ssl_mode for the ``asynch`` driver.

        This overrides the plural hook rather than the singular
        ``build_tls_connect_arg`` because the driver does not take its TLS
        configuration through one argument: ``asynch`` is its own native
        TCP protocol implementation (not a clickhouse-driver wrapper) and
        exposes ``secure`` and ``verify`` as direct named parameters on
        ``asynch.proto.connection.Connection`` - verified against asynch
        0.2.4+ and 0.3.x source. ``secure`` decides whether a TLS handshake
        happens at all and ``verify`` decides whether the server's
        certificate chain and host name are checked. Both are named
        parameters, not ``**kwargs`` pass-throughs, so there is no risk of
        silent key mismatch.

        The declared enum maps one-to-one onto those two switches:

        * ``disable``     -> ``secure=False``: plaintext native protocol.
        * ``require``     -> ``secure=True, verify=False``: encrypted, no
          certificate verification (the mode's documented meaning; a
          connection this mode accepts is trivially MITM-able and it
          exists only for servers using a private certificate that cannot
          be validated).
        * ``verify-full`` -> ``secure=True, verify=True``: encrypted, with
          the chain validated against the host's system trust store and
          the host name checked.

        No post-connect probe is needed (unlike MySQL's aiomysql surface):
        ClickHouse serves TLS on a *separate listener*, so ``secure=True``
        either completes a handshake or fails - there is no capability
        flag for a server or an attacker to withhold and no silent
        plaintext fallback.

        A custom CA bundle is rejected loudly rather than silently
        ignored: the driver's only channel for one is ``ca_certs``, a
        *filesystem path*, which a stored PEM secret cannot supply. That
        is why the connector declares no ``tls.ca_certificate`` and offers
        no CA input; a non-empty bundle arriving here means the connection
        expects verification this dialect would not actually be doing.

        The engine performs no vocabulary validation before the dialect
        sees the value (the connector.json enum is control-plane only), so
        case and surrounding whitespace are folded here and anything
        outside the declared vocabulary raises. An absent value resolves
        to the declared default, ``verify-full`` - failing closed on a
        plaintext listener rather than downgrading a connection whose
        intent was never recorded.
        """
        if ca_pem:
            raise ValueError(
                f"{self.name}: the asynch driver takes a CA bundle only as a "
                f"filesystem path (ca_certs), which a stored secret cannot "
                f"supply, so tls.ca_certificate is not supported; ssl_mode "
                f"'verify-full' validates against the system trust store"
            )
        canonical = (mode or "").strip().lower() or _DEFAULT_MODE
        if canonical == "disable":
            return {"secure": False}
        if canonical == "require":
            return {"secure": True, "verify": False}
        if canonical == "verify-full":
            return {"secure": True, "verify": True}
        raise ValueError(
            f"{self.name}: unsupported ssl_mode {mode!r}; expected one of "
            f"{', '.join(_ALL_MODES)} (matched case-insensitively)"
        )


class ClickHouseConnector(GenericSQLConnector):
    """ClickHouse connector: the CDK SQL base wired to the ClickHouse dialect."""

    dialect_class = ClickHouseDialect
