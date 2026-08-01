---
name: REPLACE
description: >
  REPLACE with a one-line description of what this connector integrates with
type: api
---

# REPLACE with Connector Name

REPLACE with a brief description of the system and what data it provides.

## Authentication

### REPLACE with Auth Type (e.g., API Key, OAuth2 Authorization Code)
- Client app required: no
- Header format: `Authorization: Bearer ${api_key}`

## Post-Auth Steps

None required.

## Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
|          |        |             |

## Rate Limits

- 60 requests per 60 seconds

## Caveats

- **`empty_table_sql` uses `DELETE FROM … WHERE 1=1`, not `TRUNCATE TABLE`.** ClickHouse's `TRUNCATE TABLE` is the natural empty-all statement and is synchronous and cheap, but the CDK tier-1 conformance check `test_empty_table_statement_is_delete_shaped` forbids any emptying statement containing `TRUNCATE`. That check is unconditional — it does not consult `sql_capabilities.stage.transactional_ddl`, which ClickHouse declares `false` (DDL commits immediately, so there is no enclosing transaction for an implicit commit to break). The lightweight delete is correct for the reset-then-append cycle: it writes a `_row_exists` mask and the rows become invisible to subsequent reads as soon as the statement returns, so the append that follows never observes pre-reset rows. Only the physical part rewrite is deferred, and that is invisible to correctness. (This is ClickHouse's lightweight `DELETE FROM`, not the older `ALTER TABLE … DELETE` mutation, whose completion genuinely is asynchronous.) The `WHERE 1=1` is required — ClickHouse rejects the bare `DELETE FROM t` that the ANSI base emits. Whether the conformance kit should exempt dialects that declare `transactional_ddl: false` is tracked in [issue #9](https://github.com/analitiq-dip-registry/clickhouse/issues/9).
