"""
High-throughput content factory + $49/mo Stripe funnel.

  cd viral-funnel
  python -m venv .venv
  .venv\\Scripts\\pip install -r requirements.txt
  copy .env.example .env
  .venv\\Scripts\\uvicorn app.main:app --host 127.0.0.1 --port 8787 --workers 1

Open http://127.0.0.1:8787  (operator)
     http://127.0.0.1:8787/join  (checkout)

One worker on purpose: the process pool + APScheduler live in-process.
Do not put this behind a multi-worker web farm without extracting the worker.
"""
