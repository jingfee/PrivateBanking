# PrivateBanking

Privat, självhostad app som hämtar mina egna bank- och korttransaktioner via
[Enable Banking](https://enablebanking.com) (PSD2, endast läsning) och lagrar dem lokalt.

- Backend: Python, FastAPI, SQLite (`backend/`)
- Frontend: SvelteKit-PWA (`frontend/`), byggs statiskt och serveras av backenden
- En container bakom Caddy, nås bara från hemnätverket och via Tailscale
- Deployas av Komodo från GitHub Container Registry

## Driftsättning (homelab med Komodo)

Vid push/merge till `main` kör GitHub Actions testerna och bygger sedan imagen
`ghcr.io/jingfee/privatebanking` med taggarna `latest` och `sha-<commit>`. Komodo hämtar den
nya imagen (automatiskt en gång per dygn eller manuellt).

Första gången:

1. Skapa en GitHub-token (classic) med endast `read:packages` och lägg in den i Komodo som
   registry-konto för `ghcr.io` (användare `jingfee`). Imagen är privat.
2. Skapa en stack i Komodo från `docker-compose.yml` i det här repot.
3. På servern, i stackens katalog: `mkdir -p data secrets && sudo chown 1000 data`.
4. Lägg Enable Banking-nyckeln i `secrets/eb.pem` och `sudo chown 1000 secrets/eb.pem`.
   (Finns inte filen när stacken startar skapar Docker en katalog med det namnet.)
5. Skapa `.env` från `.env.example` (eller som miljövariabler i Komodo).
6. Lägg till appen i Caddy (HTTPS krävs för PWA:n och BankID-redirecten).
   Appen har ingen egen inloggning, så begränsa den till hemnätverket och Tailscale:

   ```caddy
   bank.example.se {
       @outside not remote_ip private_ranges 100.64.0.0/10
       respond @outside 403
       reverse_proxy 127.0.0.1:8000
   }
   ```

7. Öppna `https://bank.example.se/accounts`, välj **Koppla bank** och logga in med BankID.

**Rulla tillbaka:** sätt `PB_TAG=sha-<commit>` och deploya om stacken.

**Backup:** databasen kopieras automatiskt till `data/backups/` före varje schemaändring
(de 10 senaste sparas). Ta även egna kopior av `data/privatebanking.db`, t.ex.
`sqlite3 data/privatebanking.db ".backup backup.db"`.

## Utveckling (Fedora)

```bash
sudo dnf install uv nodejs
```

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
