# Mental Health Support API

A bilingual English/Sinhala mental health support API with Gemini integration, local emotional trend storage, curated mindfulness activities, and hard-coded crisis escalation.

## Run

```powershell
$env:GEMINI_API_KEY = "your-key" # optional; keep this out of source control
python app.py
```

The server exposes `GET /api/health` and `POST /api/chat`.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health

$body = @{ user_id = "user-123"; message = "I feel overwhelmed"; history = @() } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/chat -Method Post -ContentType "application/json" -Body $body
```

The chat response includes `reply`, `crisis`, `analysis`, and (for non-crisis messages) a curated `activity`.

Without a Gemini key, the app uses a local supportive fallback and still performs crisis detection, trend persistence, and activity selection. The API key shared in chat should be revoked and replaced before use.

Gemini requests time out after 8 seconds by default and then use the local fallback. Adjust this with `GEMINI_TIMEOUT_SECONDS` if needed.

## Safety

This is not medical care. Crisis keyword detection is intentionally hard-coded and runs before Gemini. The Sri Lankan resources included are 1926 (National Mental Health Helpline) and 1333 (CCCline); verify local resources before production deployment. Add authentication, encryption, retention controls, consent, and professional review before handling real users.
