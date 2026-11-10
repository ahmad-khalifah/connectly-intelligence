# Deployment

Connectly Intelligence runs as three containers: PostGIS, the API and the web app
(`docker-compose.yml`, profile `app`). Any machine that runs Docker can host it, from a
laptop to a single virtual server. No paid service is required.

## 1. Local verification (first clone)

Follow "Quick start with Docker" in the README, then check:

1. <http://localhost:3000> redirects to the sign-in page, which shows the Connectly logo.
2. Sign in with the temporary password. You are asked to choose a new password.
3. The overview shows 37 states, 774 LGAs and 9,308 wards, and the Adamawa panel shows 21
   LGAs and 226 wards.
4. In the explorer, Adamawa's LGAs are coloured by modelled density.
5. The profile for Bille ward (Demsa) shows a population of 12,867 (95% interval
   8,342–19,288), labelled modelled and unverified.
6. On the Needs page, *Healthcare / LGAs in Adamawa* says there is not enough data. That is
   correct until facility data is loaded.
7. Load one local dataset (see `docs/data-ingestion.md`), run `connectly derive`, and recheck
   the Needs page.

The same checks run automatically in GitHub Actions (job `stack`) on every push.

## 2. A server

Any Linux server with Docker works. A free or low-cost VM is enough for a pilot: 2 vCPU, 4 GB
RAM and 20 GB disk handle the national boundaries comfortably.

```bash
git clone https://github.com/ahmad-khalifah/connectly-intelligence.git
cd connectly-intelligence
cp .env.example .env          # strong CONNECTLY_SECRET_KEY and POSTGRES_PASSWORD; COOKIE_SECURE=true
docker compose --profile app up -d --build --wait
docker compose exec api connectly bootstrap
docker compose exec api connectly users create --email you@example.org --name "Your Name" --role admin
```

### HTTPS

Put a reverse proxy in front of port 3000. [Caddy](https://caddyserver.com) is free and gets
certificates from Let's Encrypt automatically:

```
# /etc/caddy/Caddyfile
intelligence.example.org {
    reverse_proxy localhost:3000
}
```

With one proxy in front, set `TRUSTED_PROXY_HOPS=1` in `.env` so sign-in limits use the real
client address. Keep `COOKIE_SECURE=true`.

### Hardening checklist

- Remove the `ports:` entry of the `db` service, so the database is not reachable from outside.
- Only port 443 (and 80 for the redirect) open in the firewall.
- `CONNECTLY_ENVIRONMENT=production`, which the compose file sets for the API.
- Back up the `connectly-pgdata` volume, for example nightly:
  `docker compose exec -T db pg_dump -U connectly -Fc connectly > backup-$(date +%F).dump`
- Restore with `pg_restore -U connectly -d connectly --clean backup.dump` (inside the `db`
  container).
- Update with
  `git pull && docker compose --profile app up -d --build --wait`. Migrations run when the API
  starts.

## 3. Optional: a self-hosted language model

See `docs/ai.md`. On the same server, install Ollama, pull a model, and set
`CONNECTLY_AI_PROVIDER=ollama` in `.env`. The compose file points the API at the host's Ollama
by default (`http://host.docker.internal:11434`). Larger models need more RAM; everything works
without a model.

## Notes on the original brief's hosting suggestions

The brief suggested Vercel and managed PostgreSQL. Their free tiers have limits and change
over time, and the budget rules exclude depending on free trials. The Docker setup above runs
on any host. If you later choose a managed PostgreSQL, it must support PostGIS 3. Set
`CONNECTLY_DATABASE_URL` to it and remove the `db` service.
