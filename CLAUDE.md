---
name: ClickHouse
description: >
  Open-source column-oriented OLAP database for real-time analytics over very large datasets
type: database
---

# ClickHouse

Open-source column-oriented OLAP database for real-time analytics over very large datasets. ClickHouse stores data by column and compresses it heavily, which is why it backs product analytics, observability and reporting workloads where aggregate queries run over billions of rows.

## Authentication

### Database Credentials (username/password)
- Driver: clickhouse+asynch (async SQLAlchemy transport: the clickhouse-sqlalchemy dialect on the asynch native-protocol DBAPI)
- Default port: 9440 (TLS native listener); 9000 is the plaintext native listener
- Connection string format: `clickhouse+asynch://${username}:${password}@${host}:${port}/${database}`
- Protocol: ClickHouse's native TCP protocol, not the HTTP interface (8123 / 8443)
- A password is required; a passwordless `default` user is not a supported configuration

## Post-Auth Steps

None required.

## Caveats

- Port must be an integer, and it must agree with `ssl_mode`: TLS and plaintext are two separate listeners (9440 and 9000), so there is no in-band upgrade and changing the mode usually means changing the port.
- `ssl_mode` values are `disable` (plaintext, `secure=False`), `require` (encrypted, certificate not verified, `secure=True, verify=False`) and `verify-full` (encrypted, certificate chain and host name verified against the system trust store, `secure=True, verify=True`). Default is `verify-full`. An absent value resolves to `verify-full` so a hand-made connection fails closed rather than connecting in cleartext.
- No post-connect TLS probe is needed (unlike MySQL's aiomysql surface): ClickHouse serves TLS on its own listener, so `secure=True` either completes a handshake or fails -- there is no capability flag to withhold and no silent plaintext fallback.
- No CA certificate input is offered. The driver's only channel for a CA bundle is `ca_certs`, a filesystem path, which a stored secret cannot supply; `verify-full` validates against the host's system trust store and a bundle arriving by any other route is rejected loudly.
- `database` is the schema level; ClickHouse has no catalog above it (`sql_capabilities.catalog: none`). Defaults to `default`.
- Identifiers are quoted with backticks. ClickHouse accepts double quotes too, but backticks are unambiguous under every `*_double_quoted_*` server setting.
- Declared identifier budget is 127 characters (`max_identifier_length` / `sql_capabilities.limits.max_identifier_len`). ClickHouse documents no identifier-length constant -- a table name becomes an escaped on-disk directory name, so the ceiling is filesystem-derived -- so 127 is a conservative declared budget, not a server fact.
- Resource discovery uses `INFORMATION_SCHEMA` and excludes the `system`, `information_schema` and `INFORMATION_SCHEMA` databases.
- No API rate limits apply -- this is a direct database connection.
- **Destination writes require the target table to pre-exist.** ClickHouse's `CREATE TABLE` needs an `ENGINE` clause. `ClickHouseDialect.stage_table_sql` supplies one for the stage (`ENGINE = MergeTree ORDER BY tuple()`), but the target table's `CREATE` is CDK-rendered and there is no sanctioned dialect hook for table options, so auto-creating a target fails with `Engine must be specified`. Pre-create the target table. Needs an engine-side fix; tracked separately.
- **Nullable source columns are not preserved on write.** ClickHouse columns are `NOT NULL` by default (the inverse of ANSI) and nullable ones must be spelled `Nullable(T)`. `definition/type-map-write.json` emits bare natives and never wraps `Nullable(...)`, and the CDK renderer expresses nullability by omitting `NOT NULL` rather than by adding a marker, so CDK-rendered target DDL declares every column non-nullable and rejects NULLs from a nullable source column. Declare the columns `Nullable(T)` when pre-creating the target. Needs an engine-side fix; tracked separately.
- No upsert. ClickHouse has no `MERGE`, no `ON CONFLICT` and no `ON DUPLICATE KEY`, so `sql_capabilities.merge_form` is `none` and the engine refuses upsert streams at `configure_schema` time. The dialect deliberately does **not** override `merge_statement_sql`: the declaration already closes the path, and a hook no declaration routes a call to is dead code that reads as capability. Use `insert` or `truncate_insert`; row collapsing is a table-engine property (`ReplacingMergeTree` plus `FINAL` / `OPTIMIZE`) and is eventual.
- ClickHouse enforces no primary-key uniqueness on any engine; a primary key is a sorting/index structure, not a constraint.
- Stage scope is `real` (`sql_capabilities.stage.scope: real`, `transactional_ddl: false`) because ClickHouse commits DDL immediately. `stage_table_sql` renders `CREATE TABLE <stage> AS <target> ENGINE = MergeTree ORDER BY tuple()` -- the explicit engine override matters: `CREATE TABLE ... AS` otherwise clones the source engine, and cloning a `ReplicatedMergeTree` would copy its ZooKeeper path while cloning a `Distributed` target would fan staged rows out to the cluster. `ORDER BY tuple()` is the documented "no sorting key" spelling and sidesteps the nullable-key restriction. The engine pre-flight-`DROP`s each stage, so a leaked stage is self-healing.
- `empty_table_sql` renders a lightweight `DELETE FROM <table> WHERE 1=1`, not `TRUNCATE TABLE`. The `WHERE` is mandatory -- ClickHouse rejects the ANSI base's bare `DELETE FROM t`. `TRUNCATE TABLE` would be the natural spelling, but the CDK tier-1 conformance kit rejects any emptying statement containing `TRUNCATE` (`test_empty_table_statement_is_delete_shaped`), because `TRUNCATE` implicitly commits on several systems and would break the declared single-transaction stage cycle; the check is unconditional and does not consult `stage.transactional_ddl`. The lightweight delete is sound for reset-then-append: it writes a `_row_exists` mask and the rows stop being visible as soon as the statement returns, so the following append never sees pre-reset rows. Only the physical part rewrite is deferred. This is not the older `ALTER TABLE ... DELETE` mutation, whose completion genuinely is asynchronous.
- No bulk mechanism is declared (`sql_capabilities.bulk_load` is `{}`) and the dialect deliberately does **not** override `bulk_land`. ClickHouse has none of `copy_from`, `load_data_local_infile` or `load_job`, and the driver's `executemany` `INSERT` already *is* the native columnar block insert. Throughput comes from batch size: `write_unit` asks for 50,000 rows / 16 MiB, because small, frequent inserts cause part explosion.
- Read map: `Int256`/`UInt256` read as `Utf8` (no numeric canonical is wide enough); `Int128`/`UInt128` read as `Decimal256(39, 0)`; `Array`, `Map`, `Tuple`, `Nested`, `Variant`, `Dynamic`, `JSON`/`Object` and the geo types read as `Json`; `AggregateFunction` reads as `Binary`; `LowCardinality(...)` and `Nullable(...)` wrappers are unwrapped to the inner type's canonical.
- Write map: `Timestamp` renders `DateTime64(p, 'UTC')` at the matching precision (0/3/6/9) whatever zone the source declared; `Time32`/`Time64`/`Duration` render `Int32`/`Int64` (ClickHouse has no time-of-day or interval type); `Json`/`Object`/`List` render `String` (serialized text), not native `JSON`/`Array`/`Map`; `Utf8` and `LargeUtf8` both render `String`, which is unbounded, so there is no MySQL-style length cap.
