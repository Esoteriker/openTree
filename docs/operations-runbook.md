# Operations Runbook

## Purpose

This runbook covers service readiness, auth incidents, async dead-letter handling, and storage health.

## Readiness checklist

1. Check `GET /ready` for each service.
2. Verify Redis, Postgres, Neo4j, and Elasticsearch are reachable.
3. Confirm the parser points to the intended transformer inference URL.

## Common incidents

### Readiness failures

1. `parser-service` reports transformer not reachable.
2. `graph-service` reports Neo4j or Elasticsearch not ready.
3. `dialogue-service` reports Redis or Postgres not ready.

Remediation steps:

1. Inspect service logs for connection errors.
2. Verify env vars in the running container.
3. Retry readiness after dependencies are healthy.

### Auth failures

Symptoms:

- `401 Invalid API key` when `AUTH_MODE=api_key`.
- `401 Invalid token` or `403 Tenant mismatch` when `AUTH_MODE=jwt`.

Remediation steps:

1. Confirm `AUTH_MODE` is correct in each service.
2. Validate `TENANT_API_KEYS_JSON` or `JWT_SECRET`.
3. Ensure tenant id in header matches the JWT tenant claim.

### Async job failures and dead-letter

Symptoms:

- Job status is `failed`.
- Dead-letter events present in `turn.dead_letter`.

Remediation steps:

1. Inspect job status by `GET /v1/pipeline/jobs/{job_id}`.
2. Search logs for the job id.
3. Re-submit the original turn after dependency recovery.

Redis dead-letter inspection:

```bash
redis-cli -u "$REDIS_URL" XRANGE opentree:turn.dead_letter - +
```

## Storage checks

Postgres sessions:

```bash
psql "$POSTGRES_DSN" -c "select count(*) from dialogue_sessions;"
```

Postgres turns:

```bash
psql "$POSTGRES_DSN" -c "select count(*) from dialogue_turns;"
```

Neo4j health:

```bash
cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" -a "$NEO4J_URI" "MATCH (n) RETURN count(n);"
```

Elasticsearch ping:

```bash
curl -s "$ELASTICSEARCH_URL" | head -n 5
```

## Audit and compliance

1. Rotate secrets on a schedule.
2. Ensure encryption key changes are coordinated with storage migration.
3. Validate tenant isolation with synthetic tests before releases.
