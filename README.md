# Olympiad Practice

A private web app for practising past maths olympiad papers (IMONST, SASMO, Kangaroo, ASMO).
The child does a paper on screen. Wrong answers get one silent retry, then a photo of the
paper working. Claude labels each miss as a **careless slip** or a **technique to learn**,
explains it, and offers similar questions. The parent imports papers and watches progress.

Design: `docs/superpowers/specs/2026-11-18-olympiad-practice-design.md`

## Run locally

```sh
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
# then open .env and paste your Anthropic key after ANTHROPIC_API_KEY=
# (delete the empty SECRET_KEY= line at the top)
.venv/bin/python -m app.cli init-db
.venv/bin/python -m app.cli seed-techniques
.venv/bin/python -m app.cli create-user dad --role parent --display-name Dad
.venv/bin/python -m app.cli create-user kid --role child --display-name Kid
.venv/bin/uvicorn --factory app.main:create_app --reload
```

Open http://localhost:8000. Run the tests with `.venv/bin/pytest -q`.

To test the phone QR code at home, set `BASE_URL=http://<your-laptop-ip>:8000` and start
uvicorn with `--host 0.0.0.0`.

## Deploy to Fly.io

One small machine with a 1 GB volume (about USD 3–5/month).

```sh
brew install flyctl && fly auth login
fly launch --no-deploy --copy-config          # choose an app name and region
fly volumes create data --size 1              # same region as the app
fly secrets set SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
                ANTHROPIC_API_KEY=sk-ant-...
fly deploy --ha=false                          # SQLite needs exactly one machine
fly ssh console -C "python -m app.cli create-user dad --role parent --display-name Dad --password '...'"
fly ssh console -C "python -m app.cli create-user kid --role child --display-name Kid --password '...'"
```

The app stops when idle and starts again on the next visit (first page takes a couple of seconds).

## Backups

- Fly takes daily snapshots of the volume and keeps them for 5 days (`fly volumes snapshots list`).
- `scripts/backup.sh` copies the database on the server and downloads it to `./backups/`.
  Crops are rebuilt by re-importing; photos are only in the volume snapshots.

## Settings (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | required | Signs login cookies |
| `ANTHROPIC_API_KEY` | none | Claude API key |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model for all AI calls |
| `DATA_DIR` | `./data` | PDFs, crops, photos, backups |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Database |
| `SECURE_COOKIES` | `false` | Set `true` behind HTTPS |
| `BASE_URL` | request URL | Public URL used in QR codes |
| `UPLOAD_TOKEN_MINUTES` | `15` | How long a phone photo link works |
