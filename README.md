# PrivateBanking

Privat, självhostad app som hämtar mina egna bank- och korttransaktioner via
[Enable Banking](https://enablebanking.com) (PSD2, endast läsning) och lagrar dem lokalt.

- Backend: Python, FastAPI, SQLite (`backend/`)
- Frontend: SvelteKit-PWA (`frontend/`), byggs statiskt och serveras av backenden
- En container bakom Caddy, nås bara från hemnätverket och via Tailscale

## Köra på homelabben

1. Klona repot och skapa kataloger för data och nyckel (containern kör som uid 1000):

   ```bash
   mkdir -p data secrets && sudo chown 1000 data
   ```

2. Lägg Enable Banking-nyckeln i `secrets/eb.pem` (läsbar för uid 1000).

3. Skapa `.env` från mallen och fyll i app-id och redirect-URL:

   ```bash
   cp .env.example .env
   ```

   `EB_REDIRECT_URL` måste vara exakt en av redirect-URL:erna i Enable Banking-appen,
   t.ex. `https://bank.example.se/callback`.

4. Starta:

   ```bash
   docker compose up -d --build
   ```

5. Lägg till appen i Caddy (HTTPS krävs för PWA:n och BankID-redirecten).
   Appen har ingen egen inloggning, så begränsa den till hemnätverket och Tailscale:

   ```caddy
   bank.example.se {
       @outside not remote_ip private_ranges 100.64.0.0/10
       respond @outside 403
       reverse_proxy 127.0.0.1:8000
   }
   ```

   Kör Caddy på en annan maskin: sätt `PB_LISTEN=<homelab-ip>:8000` i `.env` och proxa till den adressen.
   Kör Caddy i Docker på samma maskin: proxa till `host.docker.internal:8000`
   (kräver `extra_hosts: ["host.docker.internal:host-gateway"]` på Caddy-containern)
   eller lägg båda i samma Docker-nätverk och proxa till `privatebanking:8000`.

6. Öppna `https://bank.example.se/accounts`, välj **Koppla bank** och logga in med BankID.
   Transaktioner hämtas direkt och sedan var `SYNC_INTERVAL_HOURS` timme.

Kom ihåg att även länka kontona under "Link accounts" i Enable Banking-kontrollpanelen
(restricted-läget hämtar bara länkade konton).

**Backup:** kopiera `data/privatebanking.db` (eller `sqlite3 data/privatebanking.db ".backup backup.db"`).

## Utveckling

```bash
cd backend && uv sync && uv run pytest
```

```bash
cd backend && DATABASE_PATH=./data/dev.db SCHEDULER_ENABLED=false uv run uvicorn app.main:create_app --factory --reload
```

```bash
cd frontend && npm install && npm run dev
```

Vite proxar `/api` och `/callback` till backenden på port 8000.

Nya databasändringar: ändra `backend/app/models.py` och kör
`uv run alembic revision --autogenerate -m "..."` i `backend/`. Migreringar körs automatiskt vid start.

## Dokument

- [Privacy Policy](PRIVACY.md)
- [Terms of Use](TERMS.md)
