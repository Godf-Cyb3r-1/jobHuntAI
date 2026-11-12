# JobHuntAI — Windows self-hosted bootstrap (v0.1.1 installer hotfix)

Open-source, multi-user job monitoring and application tracker. This repository was initialized as a new project in November 2026. It contains a **usable foundation**, not the final fully autonomous hiring platform.

## Implemented

- FastAPI browser UI with account registration/login, signed sessions and CSRF checks.
- SQLite WAL persistence and per-user job, resume and application isolation.
- Strict role and time-window match rules (unknown posting dates are excluded).
- Independent Greenhouse, Lever and Ashby job-board collectors with fault isolation and health records.
- Background scanning after server start; Telegram notifications if configured; Windows startup task.
- Resume upload (text PDF/DOCX), editable verified skills, factual per-job DOCX exports.
- Manual application-status tracker and human-written-style outreach draft.
- Windows PyInstaller exe built by GitHub Actions; installer PowerShell script.

## Not implemented yet

- The Windows distribution bundles a separate upstream OpenCode v1 executable. It is **not yet integrated as a job-matching agent** and its source is not modified. The collector does not depend on it.
- WhatsApp Cloud API (requires Meta credentials, compliant templates, and possibly charges).
- OAuth mailbox reading and automatic recruiter-response classification.
- Direct Workday/browser collectors, search-engine discovery, web-wide coverage, guaranteed live posting validity.
- Public HTTPS deployment and production rate limits, 2FA, backups, malware scanning, and security audit.
- Real-time Android push client.

**Do not expose the app directly on public HTTP.** A production deployment requires HTTPS reverse proxy, rate limiting, security hardening and monitoring. No external source can guarantee every vacancy is found or still open.

## Windows RDP installation

1. Go to **Actions → Windows build and tests → latest successful run → Artifacts** and download `JobHuntAI-Windows-x64`.
2. Extract the artifact ZIP, then extract `JobHuntAI-Windows-x64.zip` if nested.
3. Open PowerShell **as Administrator** in the extracted release directory:
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass -Force
   .\install-windows.ps1
   ```
   The installer registers a Windows Task Scheduler startup action that launches `start-server.ps1` and sets `JOBHUNTAI_HOME=C:\ProgramData\JobHuntAI` inside that process. The old `schtasks /TR` quoting problem is fixed; installing over an incomplete earlier install is supported.
4. From your RDP, browse to `http://127.0.0.1:8000`. The **first registered account becomes admin**. Choose a long unique password.
5. On Settings, check source health and add ATS company identifiers (board slugs, not URLs). Supported providers: ashby, greenhouse, lever.
6. On Profile, select `pentest`, `appsec`, and/or `llm`, actual verified skills, location restrictions, and freshness (1–30 days). Upload resume in Resumes.
7. Manually scan via an Administrator PowerShell:
   ```powershell
   $env:JOBHUNTAI_HOME='C:\ProgramData\JobHuntAI'
   & 'C:\Program Files\JobHuntAI\JobHuntAI.exe' scan
   & 'C:\Program Files\JobHuntAI\JobHuntAI.exe' health
   ```
8. Test reboot persistence: `schtasks /Query /TN JobHuntAI /V /FO LIST`; after reboot browse `http://127.0.0.1:8000` again.
9. Telegram (optional): set the `JOBHUNTAI_TELEGRAM_TOKEN` **in the Windows service process environment**, restart the task, open the bot's chat, obtain its numeric chat ID, and save it in Settings. Alerts are sent for newly matched jobs only.

The scheduled application listens on `127.0.0.1:8000` by default. For internet access, place a properly configured HTTPS reverse proxy on port 443; keep 8000/4096/5432 closed externally. On AWS open inbound 443 from users, and inbound 3389 only from your administrator IP `/32`; outbound 443 is required for fetching and optional alerts. Public IPv4 charges may apply on AWS.

## Developer setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app.py serve
```

If installed via source (rather than EXE), access the local app at `http://127.0.0.1:8000`. Set `JOBHUNTAI_HOME` to a writable data directory. Background scans run every 30 minutes by default; set `JOBHUNTAI_SCAN_SECONDS` (minimum 300). Disable with `JOBHUNTAI_AUTO_SCAN=0` when testing.

## Data and matching rules

- Per-user strict role families; profiles with unknown roles are not automatically broadened.
- Missing date means *unverified freshness*, not a fresh job. Greenhouse `updated_at` is **never** substituted for original `first_published`.
- Lever `createdAt` is a creation timestamp and may differ from publication time; date evidence is displayed.
- All matching recommendations must satisfy the user's role, place and freshness hard filters. A score is **not** an employment probability.
- No invented resume skills: DOCX exports only add user-confirmed skills and preserve extracted original text.
- The tracker reflects users' saved statuses, not private employer ATS state.

## Security and cost notes

Run the site on localhost until TLS is configured. SQLite and resumes contain personal information; keep the data directory ACL restricted, use encrypted backups, and never commit credentials or private resumes to GitHub. Free model quota, APIs, job source access and WhatsApp messaging all have separate policies/limits.
## Task Scheduler error recovery (v0.1.1)

If the original installer reported `Invalid argument/option - 'JOBHUNTAI_HOME=...'`, use the **latest** artifact: the original install script's nested cmd quoting was incorrect. Extract the new portable ZIP and rerun `install-windows.ps1` from an elevated PowerShell. Do not rerun the old release's installer script. Existing data under `C:\ProgramData\JobHuntAI` is retained. To inspect the task and logs:

```powershell
Get-ScheduledTask -TaskName JobHuntAI | Select-Object TaskName,State
Invoke-RestMethod http://127.0.0.1:8000/health
Get-Content C:\ProgramData\JobHuntAI\stdout.log -Tail 60
```
