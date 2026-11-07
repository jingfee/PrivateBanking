# PrivateBanking

Privat, självhostad app som hämtar mina egna bank- och korttransaktioner via
[Enable Banking](https://enablebanking.com) (PSD2, endast läsning) och lagrar dem lokalt.

- Backend: Python, FastAPI, SQLite (`backend/`)
- Frontend: SvelteKit-PWA (`frontend/`), byggs statiskt och serveras av backenden
- En enda container; körs bakom en reverse proxy med HTTPS och ska bara nås från ett privat nätverk

## Driftsättning

Vid push/merge till `main` kör GitHub Actions testerna och bygger sedan en image till
GitHub Container Registry (`ghcr.io/<ägare>/privatebanking`) med taggarna `latest` och
`sha-<commit>`. Servern kör `docker-compose.yml`, som använder den imagen.

1. Hämta `docker-compose.yml` och `.env.example` till servern.
2. Skapa kataloger för data och nyckel (containern kör som uid 1000):

   ```bash
   mkdir -p data secrets && sudo chown 1000 data
   ```

3. Lägg Enable Banking-nyckeln i `secrets/eb.pem` och `sudo chown 1000 secrets/eb.pem`.
   (Finns inte filen när containern startar skapar Docker en katalog med det namnet.)
4. Ange inställningarna, antingen i en `.env` bredvid `docker-compose.yml` (se `.env.example`)
   eller som miljövariabler i ditt deploy-verktyg. `EB_APP_ID` och `EB_REDIRECT_URL` krävs;
   `EB_REDIRECT_URL` måste vara exakt en av redirect-URL:erna i Enable Banking-appen.
   Låter verktyget stackens katalog skapas om, peka `PB_DATA_DIR` och `PB_KEY_FILE` på
   absoluta sökvägar utanför den.
5. Är imagen privat: logga in mot registryt med en GitHub-token som har `read:packages`
   (`docker login ghcr.io`).
6. Starta:

   ```bash
   docker compose up -d
   ```

7. Lägg appen bakom en reverse proxy med HTTPS (krävs för PWA:n och BankID-redirecten).
   Appen har ingen egen inloggning, så släpp bara igenom anrop från privata nätverk.
   Exempel för Caddy:

   ```caddy
   bank.example.com {
       @outside not remote_ip private_ranges
       respond @outside 403
       reverse_proxy 127.0.0.1:8000
   }
   ```

   Når du servern via ett VPN med egna adresser, lägg till dess adressintervall efter
   `private_ranges`.
8. Öppna `https://bank.example.com/accounts`, välj **Koppla bank** och logga in med BankID.

**Uppdatera:** `docker compose pull && docker compose up -d`, eller låt ett deploy-verktyg
hämta nya `latest`. **Rulla tillbaka:** sätt `PB_TAG=sha-<commit>` i `.env` och starta om.

**Backup:** databasen kopieras automatiskt till `data/backups/` före varje schemaändring
(de 10 senaste sparas). Ta även egna kopior av `data/privatebanking.db`, t.ex.
`sqlite3 data/privatebanking.db ".backup backup.db"`.

## Utveckling

Kräver [uv](https://docs.astral.sh/uv/) och Node.js 22.

```bash
./dev.sh
```

Öppna http://localhost:5173. Första gången fylls `backend/data/dev.db` med påhittade
transaktioner; `./dev.sh --reset` börjar om.

För att testa bankkopplingen lokalt: skapa en **sandbox**-app i Enable Banking med
redirect-URL `http://localhost:5173/callback`, lägg nyckeln i `secrets/eb-sandbox.pem` och
kopiera `.env.dev.example` till `.env.dev`. Använd aldrig produktionsnyckeln lokalt.

Arbeta på en branch och öppna en pull request. CI kör testerna, och först när de går igenom
mergar du till `main`, vilket bygger en ny image.

Tester och kontroller:

```bash
cd backend && uv run pytest -q
```

```bash
cd frontend && npm run check
```

Ny databasändring: ändra `backend/app/models.py` och kör
`uv run alembic revision --autogenerate -m "..."` i `backend/`.

## Dokument

- [Privacy Policy](PRIVACY.md)
- [Terms of Use](TERMS.md)
