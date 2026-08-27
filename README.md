# Mental Health Support API

A bilingual English/Sinhala mental health support API with Gemini integration, local emotional trend storage, curated mindfulness activities, and hard-coded crisis escalation.

## Run

```powershell
$env:GEMINI_API_KEY = "your-key" # optional; keep this out of source control
python app.py
```

The server exposes `GET /api/health` and `POST /api/chat`.

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for the complete endpoint reference.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health

$body = @{ user_id = "user-123"; message = "I feel overwhelmed"; history = @() } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/chat -Method Post -ContentType "application/json" -Body $body
```

The chat response includes `reply`, `crisis`, `analysis`, and (for non-crisis messages) a curated `activity`.

Without a Gemini key, the app uses a local supportive fallback and still performs crisis detection, trend persistence, and activity selection. The API key shared in chat should be revoked and replaced before use.

Gemini requests time out after 8 seconds by default and then use the local fallback. Adjust this with `GEMINI_TIMEOUT_SECONDS` if needed.

## Deploy to Render

1. Push this repository to GitHub.
2. In Render, choose **New > Blueprint** and select the repository. Render will use `render.yaml`.
3. In the service environment settings, add `GEMINI_API_KEY` as a secret. The app works without it using the local fallback.
4. Open the deployed URL and check `/api/health`.

The default model is `gemini-3.5-flash`. Override it with the `GEMINI_MODEL` environment variable when needed.

The service uses Render's ephemeral filesystem, so the SQLite trend database is reset when the service is redeployed or restarted. Use a managed database and update `DB_PATH` before storing production user data.

## Safety

This is not medical care. Crisis keyword detection is intentionally hard-coded and runs before Gemini. The Sri Lankan resources included are 1926 (National Mental Health Helpline) and 1333 (CCCline); verify local resources before production deployment. Add authentication, encryption, retention controls, consent, and professional review before handling real users.
