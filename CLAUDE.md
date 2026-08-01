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

- **Destination writes require the target table to already exist.** ClickHouse's `CREATE TABLE` is invalid without an `ENGINE` clause. The connector supplies one for its own stage table (`ENGINE = MergeTree ORDER BY tuple()`), but the *target* table's DDL is rendered by the CDK, which has no sanctioned dialect hook for table options. Pointing a stream at a target table that does not already exist fails with `Engine must be specified`. Pre-create the destination table with the appropriate engine, sorting key, and partitioning before writing. A core-side fix (dialect hook or CDK extension) is tracked separately.
