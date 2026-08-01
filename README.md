[![Status: unverified](https://img.shields.io/badge/status-unverified-orange)](https://github.com/analitiq-dip-registry)
[![Latest release](https://img.shields.io/github/v/release/analitiq-dip-registry/clickhouse)](https://github.com/analitiq-dip-registry/clickhouse/releases)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

# ClickHouse

Open-source column-oriented OLAP database for real-time analytics over very large datasets. ClickHouse stores data by column and compresses it heavily, which is why it backs product analytics, observability and reporting workloads where aggregate queries run over billions of rows.

## What is this?

This is a **connector** -- a configuration that defines how to authenticate with ClickHouse and what data is available for reading and writing. It does not move data by itself. Instead, it is used by the [Analitiq](https://analitiq-app.com) data integration platform or the open-source [Analitiq Engine](https://github.com/analitiq-ai/analitiq-engine) to set up data pipelines.

## How to use this connector

There are two ways to use this connector:

### Option 1 -- Analitiq Cloud (no setup required)

All connectors from this registry are automatically available on [analitiq-app.com](https://analitiq-app.com). Simply log in, select the connector, and follow the on-screen instructions to connect your database.

### Option 2 -- Open Source (self-hosted)

All connectors are open source and free to use. To get started:

1. Clone the [analitiq-engine](https://github.com/analitiq-ai/analitiq-engine) repository
2. Install the Claude plugin `analitiq-plugin-dataflow`
3. Launch Claude in the root directory of `analitiq-engine`
4. Tell it: *"I need to move data from X to Y"*

The `analitiq-plugin-dataflow` plugin will automatically fetch the required connectors from the [Analitiq DIP Registry](https://github.com/analitiq-dip-registry) and set up the data flow pipeline for you.

## Prerequisites

- A running ClickHouse server, or a ClickHouse Cloud service
- Network access from the Analitiq platform to the server's **native TCP protocol** listener -- port 9440 for TLS, port 9000 for plaintext. This connector does not use the HTTP interface (8123 / 8443).
- A ClickHouse user with a password, holding `SELECT` on the databases you want to read
- For destination use, additionally `INSERT`, `CREATE TABLE`, `DROP TABLE` and `TRUNCATE` on the target database -- and a target table that already exists (see [Limitations](#limitations))

## Authentication

ClickHouse uses standard database credentials (username and password). The connector speaks ClickHouse's native protocol through the `clickhouse+asynch` SQLAlchemy transport and connects as:

```
clickhouse+asynch://${username}:${password}@${host}:${port}/${database}
```

A password is required. A stock server's passwordless `default` user is not a supported configuration for this connector.

### How to get your credentials

1. Connect to your ClickHouse server as an administrator (for example with `clickhouse-client`)
2. Create a dedicated user for the integration (recommended):
   ```sql
   CREATE USER analitiq IDENTIFIED WITH sha256_password BY 'your_secure_password';
   ```
3. Grant read access to the database you want to move data out of:
   ```sql
   GRANT SELECT ON analytics.* TO analitiq;
   ```
4. If ClickHouse is also a **destination**, grant the privileges the write cycle needs:
   ```sql
   GRANT INSERT, CREATE TABLE, DROP TABLE, TRUNCATE ON analytics.* TO analitiq;
   ```
5. Note the host, the native port (9440 with TLS, 9000 without), the database name (`default` on a stock server), the username and the password

On ClickHouse Cloud, the service's connection panel gives you the host, the native port (9440) and the `default` user's password; create a dedicated user with the statements above if you prefer least privilege.

## Connection settings

| Setting  | Required | Default       | Notes                                                                                    |
|----------|----------|---------------|------------------------------------------------------------------------------------------|
| Host     | yes      | --            | Hostname or IP serving the native TCP listener.                                           |
| Port     | yes      | `9440`        | Integer. Must agree with SSL Mode: 9440 for `require`/`verify-full`, 9000 for `disable`.   |
| Database | yes      | `default`     | A ClickHouse database is the schema level; there is no catalog above it.                  |
| Username | yes      | `default`     | ClickHouse user.                                                                          |
| Password | yes      | --            | Stored as a secret. Required.                                                             |
| SSL Mode | no       | `verify-full` | One of `disable`, `require`, `verify-full`.                                               |

## SSL mode

`ssl_mode` maps onto the two switches the `asynch` driver exposes:

| Value         | Meaning                                                                              |
|---------------|----------------------------------------------------------------------------------------|
| `disable`     | Plaintext native protocol (`secure=False`). Usually port 9000.                          |
| `require`     | Encrypted, server certificate **not** verified (`secure=True, verify=False`).           |
| `verify-full` | Encrypted, certificate chain and host name verified against the system trust store. *(default)* |

ClickHouse serves TLS on a **separate listener** from plaintext -- there is no STARTTLS-style in-band upgrade -- so `secure=True` either completes a handshake or fails outright. That is why this connector needs no post-connect encryption probe: there is no capability flag a server or an attacker can withhold to silently drop the session to cleartext. It also means changing `ssl_mode` usually means changing the port too.

`require` exists only for servers presenting a private certificate that cannot be validated; a connection it accepts is trivially interceptable.

## Limitations

### Destination writes require the target table to already exist

ClickHouse's `CREATE TABLE` is invalid without an `ENGINE` clause. The connector supplies one for its own stage table (`ENGINE = MergeTree ORDER BY tuple()`), but the **target** table's `CREATE` is rendered by the CDK, which emits no table options and offers no sanctioned dialect hook for them. Pointing a stream at a target table that does not already exist therefore fails with `Engine must be specified`. Create the destination table yourself first, choosing the engine, sorting key and partitioning that suit the data. Lifting this needs an engine-side answer and is tracked separately; it is not something the connector can fix on its own.

### Nullable source columns are not preserved on write

ClickHouse columns are `NOT NULL` by default -- the inverse of ANSI SQL -- and a column that accepts NULLs must be declared `Nullable(T)` explicitly. The write map emits bare native types and never wraps `Nullable(...)`, while nullability is applied by the CDK renderer, which expresses "nullable" by *omitting* `NOT NULL` rather than by adding a marker. CDK-rendered target DDL therefore declares every column non-nullable, and NULLs arriving from a nullable source column are rejected. Where you pre-create the target table yourself, declare the affected columns `Nullable(T)`. Lifting this needs an engine-side answer and is tracked separately.

### Other limitations

- **No upsert** -- ClickHouse implements none of the three merge grammars: no SQL-standard `MERGE`, no `ON CONFLICT`, no `ON DUPLICATE KEY`. The connector declares `merge_form: none`, so the engine refuses upsert streams at handshake time rather than silently duplicating rows. Use `insert` or `truncate_insert`. If you need row collapsing, it is a *table engine* property on the ClickHouse side: create the target as a `ReplacingMergeTree` and read it with `FINAL` (or run `OPTIMIZE ... FINAL`), accepting that deduplication is eventual.
- **No primary-key uniqueness** -- ClickHouse enforces none, on any engine. A primary key is a sorting/index structure, not a constraint.
- **Stage tables are real tables** -- ClickHouse commits DDL immediately, so the per-batch stage is a real `MergeTree` table created in the target database and dropped outside any transaction. The engine pre-flight-`DROP`s each stage before creating it, which is what makes an interrupted cycle self-healing rather than leaving orphans behind.
- **Batches land via `executemany`** -- ClickHouse has no `COPY FROM`, no `LOAD DATA LOCAL INFILE` and no load-job API, which are the only mechanisms the capability vocabulary can name, so no bulk mechanism is declared. What the driver performs for an `executemany` `INSERT` *is* ClickHouse's native columnar block insert, i.e. already the fast path. Throughput comes from batch size instead: the connector asks for up to 50,000 rows or 16 MiB per write, because small, frequent inserts are what ClickHouse punishes with part explosion.
- **Native protocol only** -- the connector uses the native TCP interface, not the HTTP interface, so an endpoint or proxy that exposes only 8123/8443 will not work.
- **No custom CA bundle** -- the driver's only channel for one is a filesystem path, which a stored secret cannot supply, so the connector offers no CA certificate input. `verify-full` validates against the host's system trust store, and a CA bundle arriving by any other route is rejected loudly rather than silently ignored.
- **No catalog level** -- a ClickHouse database is the schema level and nothing sits above it (`catalog: none`), so there is no catalog to address.
- **Identifier budget of 127 characters** -- ClickHouse documents no identifier-length constant; a table name becomes an escaped on-disk directory name, so the real ceiling is filesystem-derived and version-dependent. 127 is a deliberately conservative declared budget that the engine composes generated stage names within, not a claim about your server.
- **System databases are hidden from discovery** -- `system`, `information_schema` and `INFORMATION_SCHEMA` are excluded.
- **256-bit integers are read as text** -- `Int256`/`UInt256` exceed every numeric canonical, so they are read as `Utf8` to stay lossless. `Int128`/`UInt128` are read as `Decimal256(39, 0)`.
- **Complex types are read as JSON** -- `Array`, `Map`, `Tuple`, `Nested`, `Variant`, `Dynamic`, `JSON`/`Object` and the geo types (`Point`, `Ring`, `LineString`, `MultiLineString`, `Polygon`, `MultiPolygon`) all read as the `Json` canonical. `AggregateFunction` states read as `Binary` and are only meaningful to ClickHouse itself.
- **Time-of-day and interval values are written as integers** -- ClickHouse has no time-of-day or interval column type, so the `Time32`, `Time64` and `Duration` canonicals are written as `Int32`/`Int64` counts in their declared unit.
- **Written timestamps are always UTC** -- every `Timestamp` canonical renders `DateTime64(p, 'UTC')` at the matching precision (0, 3, 6 or 9), whatever zone the source declared.
- **Written JSON, arrays and objects are strings** -- the `Json`, `Object` and `List` canonicals render `String` (serialized text), not ClickHouse's native `JSON`, `Array` or `Map` types.
- **No rate limits** -- this is a direct database connection; no API rate limits apply. Heavy queries do, however, compete with the rest of your ClickHouse workload.

## For AI agents

This connector includes `CLAUDE.md` and `AGENTS.md` files -- machine-readable references used by AI agents and agentic frameworks. They document authentication types, caveats, and connection details for programmatic use. Both files are kept identical -- `CLAUDE.md` is for Claude Code, `AGENTS.md` is for other agent frameworks.

## Create a connector to any system

You can create a new connector to any API or database using Claude and the Analitiq connector builder plugin:

1. Install [Claude Code](https://claude.ai/code)
2. Install the connector builder plugin:
   ```
   claude plugin add analitiq-dip-registry/analitiq-plugin-connector-builder
   ```
3. Launch Claude and say: *"I want to create a connector for [system name]"*
4. The plugin will interview you about the system, research its API documentation, and generate the full connector with all required files

No coding required -- the plugin handles authentication research, endpoint schema generation, and file creation automatically.

![Example of Claude building a connector](media/example_1.png)

## Contributing

All connectors in this registry are community-maintained and live at [github.com/analitiq-dip-registry](https://github.com/analitiq-dip-registry). To add new endpoints or improve an existing connector, install the [connector builder plugin](https://github.com/analitiq-dip-registry/analitiq-plugin-connector-builder) and follow its instructions.

## Links

- [ClickHouse Documentation](https://clickhouse.com/docs)
- [Analitiq Cloud](https://analitiq-app.com)
- [Analitiq Engine (open source)](https://github.com/analitiq-ai/analitiq-engine)
