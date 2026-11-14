# JobHuntAI

Self-hosted Windows job discovery backend + native Android companion. **No automatic applications.**

## Status
V1 foundation. The backend now includes built-in Lever and Ashby company boards and best-effort public Bing RSS dorking across enterprise career domains. Strict role filtering remains enabled. Search engines may return no RSS results, and this does not guarantee full portal coverage; full enterprise-specific crawlers and AI calibration remain planned. Do not assume the project covers every Indian job portal or that undated jobs are verified as published recently.

## Windows quick start
1. Install Python 3.11+.
2. `cd backend` and `py -m venv .venv`.
3. `.venv\Scripts\pip install -r requirements-dev.txt`.
4. No API key signup is needed: the Windows server generates its own private pairing key in `backend/.jobhunt-api-key` and prints it in the console. This is unrelated to OpenCode/DeepSeek. Set `JOBHUNT_OPENCODE_URL` only if your OpenCode server uses a non-default address.
5. Run `run_windows.bat`. API listens at `http://127.0.0.1:8765`.
6. Company ATS feeds are automatically seeded (Lever and Ashby) and a Bing RSS index discovery adapter checks multiple enterprise and ATS domains. You can extend sources via `PUT /api/feeds`; list active configuration at `/api/sources`.
7. Use Swagger at `http://127.0.0.1:8765/docs` to configure profile and trigger a scan.

**Important:** OpenCode must be running, authenticated if configured, and have a working model selected. Without a reachable model, conservative heuristic scoring applies. Do not expose the API or OpenCode to the public internet without HTTPS and authentication.

## Android
Open `android/` in Android Studio or trigger the GitHub Actions APK build. Set the server's HTTPS URL and the same API key in the app. For remote use, supply a private network/tunnel HTTPS endpoint. Firebase push needs a Firebase project, Android `google-services.json`, and backend service account credentials; see Android README. Never commit secrets or the Firebase service account.

## Freshness caveat
Lever/Greenhouse/Ashby feeds and search results may omit authoritative published-at timestamps. Such items are intentionally shown as **unverified date** and **cannot trigger a high-confidence alert**; they are not described as confirmed fresh/active. Initial window defaults to 30 days and incremental search window to 1 day for sources supplying trusted posting dates. Every 15 minutes is the scheduler interval, not a guarantee of upstream publication indexing.

## Security
API is bearer-token protected (except health). Keep `.jobhunt-api-key`, `.env`, service accounts, resumes and SQLite database off GitHub. Android app currently stores the API token in app-private preferences (not hardware-backed encrypted storage); use a dedicated scoped token, do not use a reused account password, and use HTTPS for remote connections. User-controlled remote commands are limited to scan/pause/resume.
