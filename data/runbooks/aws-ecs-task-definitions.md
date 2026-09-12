# AWS ECS Task Definition Runbook

## Environment variables

ECS task definitions inject configuration through `environment` and `secrets`.
Use `secrets` with AWS Secrets Manager or SSM Parameter Store for database
passwords, API keys, and TLS material. Plain `environment` is only for
non-sensitive values such as `LOG_LEVEL`, `AWS_REGION`, and feature flags.

To apply a change, register a new task definition revision and update the
service with `--force-new-deployment`. Existing tasks do not pick up env
var edits until they are replaced.

## CPU, memory, and networking

Fargate tasks must use a valid CPU/memory pair (for example 256/512 or
1024/2048). awsvpc mode gives each task its own ENI; security groups on
the task must allow egress to the database and inbound from the load
balancer health-check port.

## Common failures

- `ResourceInitializationError`: execution role cannot pull the image or
  read secrets.
- Tasks stuck in PENDING: subnet has no IPs or Fargate capacity in that AZ.
- App boots then dies: missing required env var (`DATABASE_URL`, `REDIS_URL`).
