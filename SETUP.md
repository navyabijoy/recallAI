# recallAI — setup (multi-user)

recallAI now supports multiple users: everyone signs in with Google and gets their
own isolated knowledge graph, memory model, solves, and extension API key.

## 1. Backend env

```bash
cp backend/.env.example backend/.env
# generate a secret:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Put that value in `SECRET_KEY`.

## 2. Google OAuth credentials

1. Go to <https://console.cloud.google.com/> → create/select a project.
2. **APIs & Services → OAuth consent screen** → External → add your email as a test user.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → type **Web application**.
4. Under **Authorized redirect URIs** add exactly:
   ```
   http://localhost:8000/api/auth/google/callback
   ```
5. Copy the **Client ID** and **Client secret** into `backend/.env`
   (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).

## 3. Database

**Option A — SQLite (zero setup, single machine).** Leave `DATABASE_URL` as the default.
Tables are created automatically on startup.

**Option B — Postgres (recommended for real multi-user).**
1. Create a free database at <https://neon.tech> (or Supabase) and copy the connection string.
2. Set it in `backend/.env` (note the `+psycopg` driver):
   ```
   DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/dbname?sslmode=require
   ```
3. Create the schema — either let startup's `create_all` bootstrap it, or use Alembic:
   ```bash
   cd backend
   ../backend/venv/bin/alembic revision --autogenerate -m "init"
   ../backend/venv/bin/alembic upgrade head
   ```

## 4. Install & run

```bash
# backend
./backend/venv/bin/pip install -r backend/requirements.txt
./backend/venv/bin/uvicorn backend.main:app --reload --port 8000

# frontend (webpack dev — Turbopack has a runaway bug in this Next build)
cd frontend && npm run dev
```

Open <http://localhost:3000> → you'll be sent to **/login** → **Sign in with Google**.
After consent you land back logged in, and your topic graph is seeded fresh.

## 5. Browser extension (per user)

1. In the web app go to **Settings** → **Generate new key**, copy it.
2. Load `extension/` as an unpacked extension (see `extension/README.md`), open its popup,
   paste the **Backend URL** (`http://localhost:8000`) and the **API key**, Save.
3. Solve a problem on LeetCode/Codeforces — it lands under your account.

## Notes
- The web app authenticates with a Bearer JWT (stored in the browser); the extension
  authenticates with the API key. Neither uses cookies.
- Every data endpoint lives under `/api/me/*` and derives the user from the token, so
  users can only ever access their own data.
- Moving from SQLite to Postgres starts with a fresh database (old local demo data does
  not carry over).
