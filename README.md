Follow these steps:

```powershell
# 1. Clone the repository
git clone <YOUR_GIT_URL>
cd <repo-folder>

# 2. Install dependencies
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
npm install
npm --prefix frontend install

# 3. Connect Neon
npx neon link
npx neon deploy

# 4. Add Clerk keys to .env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_publishable_key
CLERK_SECRET_KEY=your_secret_key
CLERK_WEBHOOK_SIGNING_SECRET=your_webhook_signing_secret

# 5. Prepare the database and Redis
alembic upgrade head
docker compose up -d redis

# 6. Start the backend
uvicorn app.main:app --reload

# 7. Start the worker in another terminal
.venv\Scripts\Activate.ps1
arq app.worker.WorkerSettings

# 8. Start the frontend in another terminal
npm --prefix frontend run dev
```

This project is built with:

- FastAPI
- Next.js (with TypeScript)
- Neon
- Redis
- Clerk
- Tesseract
