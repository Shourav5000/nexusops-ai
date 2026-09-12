# AWS ECS Health Checks and Rolling Restarts

## Target group health checks

The load balancer marks a target unhealthy if the health-check path does
not return HTTP 200 within the timeout. Confirm:

1. Container `portMappings` match the target group port.
2. Security group allows the load balancer to reach that port.
3. The app binds `0.0.0.0`, not `localhost`.
4. Grace period (`healthCheckGracePeriodSeconds`) is long enough for
   migrations and cache warmup.

Unhealthy replacements that never stabilize usually mean a bad image,
wrong env, or a database connection that fails on boot.

## Rolling restart

A graceful rolling restart replaces tasks without a full outage:

```
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

Set `minimumHealthyPercent` to 100 and `maximumPercent` to 200 so ECS
starts new tasks before draining old ones. If the service is failing
health checks, inspect stopped-task reason codes in the ECS console
before forcing another deployment.
