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

- **All write-path DDL columns are nullable.** `definition/type-map-write.json` wraps every native type in `Nullable(T)`. CDK-rendered target DDL therefore declares all columns nullable, even when the source column was `NOT NULL`. This is required because ClickHouse columns are `NOT NULL` by default (the inverse of ANSI SQL), and the type map carries no per-column nullability metadata. Per-column propagation (nullable source → `Nullable(T)`, non-nullable source → bare `T`) requires a CDK DDL-renderer hook that does not yet exist.
