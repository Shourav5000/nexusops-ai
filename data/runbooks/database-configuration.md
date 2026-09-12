# Database Configuration Runbook

## Connection strings

Applications should read `DATABASE_URL` (or equivalent) from the task
secret, not from a checked-in `.env`. Prefer a pooled URL:

`postgresql://app_user@db.internal:5432/appdb?sslmode=require`

Enable TLS (`sslmode=require` on Postgres, `encrypt=true` on SQL Server).
Do not embed passwords in the task definition JSON.

## Pooling and timeouts

Set pool size from task CPU/memory. A 512 MB Fargate task should stay
near 5–10 connections. `connect_timeout` of 5 seconds and idle recycle
under 10 minutes avoid stale connections through NAT gateways.

ECS rolling deploys briefly double connection count. Size the database
`max_connections` for `desired_count * 2 * pool_size`.

## Connectivity failures

- Timeout from ECS: task security group missing egress 5432/3306, or
  database SG missing ingress from the task SG.
- Auth failed: rotate the secret and force a new deployment so tasks
  reload credentials.
- Too many connections: lower pool size or add PgBouncer / RDS Proxy
  in front of the instance.
