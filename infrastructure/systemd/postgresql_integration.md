---
title: PostgreSQL integration
description: 'Set the database URL in `/etc/justnews/global.env` (adjust credentials/host):'

tags: ["adjust", "credentials", "database"]
---

# PostgreSQL integration

Set the database URL in `/etc/justnews/global.env` (adjust credentials/host):

```
JUSTNEWS_DB_URL=postgresql://user:pass@localhost:5432/justnews
```

## Verification (on-host)

Use the helper to verify connectivity quickly:

```
sudo ./infrastructure/systemd/helpers/db-check.sh
```

If `psql` is available, the script runs `SELECT 1`. Otherwise, it checks the Memory service health endpoint as a proxy.

See also: `infrastructure/systemd/QUICK_REFERENCE.md` for the minimal env examples.

