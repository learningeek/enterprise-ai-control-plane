# System overview

```
Enterprise Users / Applications
          |
     AI Gateway Layer
          |
  Usage Collection Engine
          |
  -----------------------------
  |            |              |
Metering    Policy Engine   AI Intelligence
Engine                       (forecasting, anomaly, recommendations)
  |            |              |
Cost         Governance     Local ML
Analytics    Rules          Models
          |
  Enterprise Integration Layer
          |
  -----------------------------
  |       |         |        |
 SSO    Billing    ITSM    FinOps
Okta/  (SAP)   (ServiceNow) (Cloud)
Entra
```

Every module downstream of the Usage Collection Engine consumes the same `AIUsageEvent` schema
(`specs/event-schema.md`) — there is no separate data model per module.
