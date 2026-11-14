# JobHuntAI

Self-hosted Windows job discovery backend + native Android companion. **No automatic applications.**

## Status
V1 foundation. ATS collection and strict role-family matching are implemented. Public search-engine discovery, company-directory expansion, verified posting dates for ATS feeds, and rich AI calibration remain planned. Do not assume the project covers every Indian job portal or that undated jobs are verified as published recently.

## Windows quick start
1. Install Python 3.11+.
2. `cd backend` and `py -m venv .venv`.
3. `.venv\Scripts\pip install -r requirements-dev.txt`.
4. Copy `.env.example` to `.env`; set `JOBHUNT_API_KEY` to a random string at least 24 characters long. Set `JOBHUNT_OPENCODE_URL` to your reachable OpenCode server URL.
5. Run `run_windows.bat`. API listens at `http://127.0.0.1:8765`.
6. Add ATS feeds through authenticated `PUT /api/feeds`, e.g. `[{"type":"greenhouse","name":"example"},{"type":"lever","name":"example"}]` with actual company board IDs.
7. Use Swagger at `http://127.0.0.1:8765/docs` to configure profile and trigger a scan.

**Important:** OpenCode must be running, authenticated if configured, and have a working model selected. Without a reachable model, conservative heuristic scoring applies. Do not expose the API or OpenCode to the public internet without HTTPS and authentication.

## Android
Open `android/` in Android Studio or trigger the GitHub Actions APK build. Set the server's HTTPS URL and the same API key in the app. For remote use, supply a private network/tunnel HTTPS endpoint. Firebase push needs a Firebase project, Android `google-services.json`, and backend service account credentials; see Android README. Never commit secrets or the Firebase service account.

## Freshness caveat
Lever/Greenhouse feeds used here often omit authoritative published-at timestamps. Such items are intentionally shown as **unverified date** and **cannot trigger a high-confidence alert**; they are not described as confirmed fresh/active. Initial window defaults to 30 days and incremental search window to 1 day for sources supplying trusted posting dates. Every 15 minutes is the scheduler interval, not a guarantee of upstream publication indexing.

## Security
API is bearer-token protected (except health). Keep `.env`, service accounts, resumes and SQLite database off GitHub. Android app currently stores the API token in app-private preferences (not hardware-backed encrypted storage); use a dedicated scoped token, do not use a reused account password, and use HTTPS for remote connections. User-controlled remote commands are limited to scan/pause/resume.
