# Sharing The UI_test App

This app is a Flask site backed by PostgreSQL, so a public link only works while:

- the web server is running
- the database is reachable

There are two practical ways to share it.

## 1. Fast temporary public link

Run the app locally:

```bash
cd /tmp/ui_test_worktree
DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/DBNAME" \
MPLCONFIGDIR=/tmp/mpl \
python run.py
```

Then expose port `5000` with a tunnel:

### Option A: ngrok

```bash
ngrok http 5000
```

### Option B: cloudflared

```bash
cloudflared tunnel --url http://127.0.0.1:5000
```

Share the public URL shown by the tunnel tool.

This is the fastest way to let other people see the site, but the link only works while your machine and Flask process stay running.

## 2. Always-on hosted link

Deploy the app to a Python web host and point it at a persistent PostgreSQL database.

The app is already prepared to run with Gunicorn:

```bash
gunicorn "run:app"
```

Typical deployment steps:

1. Clone the `UI_test` code on the host.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set environment variables:
   - `DATABASE_URL`
   - `SECRET_KEY`
4. Apply the schema once:

```bash
psql "$DATABASE_URL" -f schema/schema.sql
```

5. Start the app with:

```bash
gunicorn "run:app"
```

## Important note about generated files

The app writes generated outputs under:

- `app/static/generated`

If you deploy to a platform with temporary local disk, those files may disappear after restarts or redeploys. They can still be regenerated, but they are not guaranteed to persist unless the host supports persistent storage.
