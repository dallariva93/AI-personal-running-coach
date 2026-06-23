# Render / Railway / Heroku-style process declaration.
# Applies migrations, then serves on the platform-provided $PORT.
release: python -m app.cli migrate
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --forwarded-allow-ips="*"
