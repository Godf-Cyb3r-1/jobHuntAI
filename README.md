# JobHuntAI v0.2 — Autonomous OpenCode v1 Windows edition

Open-source, multi-user job monitoring and application tracker. This repository was initialized as a new project in November 2026. It contains a **usable foundation**, not the final fully autonomous hiring platform.

## Autonomous OpenCode v1 engine

This release replaces the previous manual keyword-only recommendation path with
**a real OpenCode v1.19.5 server, agents and a local MCP integration**. The web UI
is a control panel, not the decision-making engine.

On Windows startup JobHuntAI:

1. Starts its persistent scheduler and scans all registered public ATS boards.
2. Independently discovers new ATS employer boards from free public search RSS where available,
   validates their official feeds, and adds successful boards to the registry.
3. Applies deterministic role, location, freshness and verified-profile hard gates.
4. Sends eligible user/job pairs to a dedicated **OpenCode job-matcher agent** through
   authenticated localhost session APIs. If OpenCode/LLM is unavailable, the job is
   *pending* rather than pretending it was reviewed.
5. Requires valid AI JSON, an affirmative evaluation and a strict score threshold before
   adding a personal recommendation. Invalid responses are retried with bounded backoff.
6. Creates an automatic evidence-backed DOCX resume copy and an AI outreach draft for
   every accepted job when the user uploaded a resume. The original remains unchanged.
7. Sends Telegram alerts for newly AI-approved jobs and updates the web job feed.
8. Keeps worker states, provider failures and request counts in the local database.

Agent roles: `job-matcher`, `job-discovery`, and `outreach-writer`.
The v1 runtime is the upstream open-source binary (not a modified OpenCode source fork).
The application implements its own orchestration around OpenCode.

Bundled read-only Model Context Protocol (MCP) tools:
`jobhunt_public_jobs`, `jobhunt_source_health`, and
`jobhunt_verify_public_board`. They never expose users' private resumes,
credentials or application history to MCP tools.

## Initial AI setup (one-time, per server)

1. Install the latest Windows .exe in Administrator PowerShell or use the setup EXE.
2. Open `http://127.0.0.1:8000` **inside RDP only** and create the first/admin account.
3. Go to **Settings → Autonomous OpenCode AI engine**.
4. Obtain a free OpenRouter API key at https://openrouter.ai/settings/keys and enter it.
5. Select an actually available free model. Default is
   `openrouter/deepseek/deepseek-v4-flash-0731:free`, but free models and API limits change.
   If that exact model is no longer usable, choose a supported free model ID.
6. Save. The background supervisor starts the bundled `opencode.exe` on
   `127.0.0.1:4096` with Basic authentication, then evaluates matches periodically.
   Restart the **JobHuntAI** Scheduled Task when changing models on an already running
   OpenCode instance.
7. Under **Profile**, provide strict professional role families, verified skills,
   location and freshness window. Under **Resumes**, upload your authentic DOCX/PDF.
8. See progress in **AI Workers**. Only AI-approved jobs appear under **Matching jobs**.

OpenRouter's free tier has daily request limits. This application defaults to an
internal limit of 30 model calls/day, adjustable via `JOBHUNTAI_AI_DAILY_LIMIT`.
The default AI-score threshold is 78 (`JOBHUNTAI_MIN_AI_SCORE`). No AI key means
**no AI-approved matches**, not a silent downgrade to keyword-only results.

## Telegram setup (no paid server or inbound ports)

1. Create a Telegram bot using BotFather.
2. As the first registered admin, open Settings and save the Telegram Bot API token.
3. Each user opens Settings and copies the one-time `/start <linking-code>` command
   into that bot's chat. No numeric Telegram chat ID is needed.
4. The bot polls updates over outbound HTTPS; it supports `/jobs` and `/status`.
   New AI-approved matches are delivered automatically once the account is linked.

## Implemented in this release

- Multi-user login/registration, protected sessions, CSRF and tenant-scoped records.
- Autonomous supervisor and scheduled Windows background execution.
- Public ATS fetching from Ashby, Lever, Greenhouse with failure isolation.
- Periodic free ATS discovery, limited to validated boards.
- OpenCode v1 autonomous matching with provider limits, validation and retries.
- Automatic factual DOCX copy and natural-language outreach draft generation.
- Local MCP server with three public-job-source tools and no private-data tools.
- Web AI worker/queue dashboard and one-time Telegram linking.
- Application tracker (user status recording, **not** employer-side ATS status).
- Tested native Windows executable and installer pipeline in GitHub Actions.

## Not implemented yet

- Source-level fork/modifications to OpenCode itself (integration uses pinned upstream v1).
- General-purpose unrestricted browser crawling of every company site, Workday,
  authenticated job portals, or CAPTCHA-protected sites.
- Automatic email sending, mailbox OAuth / recruiter reply ingestion, and automatic
  employer application-status synchronization.
- Official WhatsApp Cloud API (Meta setup / template costs apply).
- Android client and mobile push alarm-style notifications.
- Public HTTPS deployment and complete security review, backup and rate-limit hardening.
- Live provider inference cannot be end-to-end tested without the user's private API key.

**Important:** Neither an AI model nor a scraper can guarantee discovering every
job on the web or perfectly interpreting every employer requirement. Employer source
verification and strict eligibility are intentionally required; errors remain visible.

## Windows RDP installation

1. Go to **Actions → Windows build and tests → latest successful run → Artifacts** and download `JobHuntAI-Windows-x64` (choose a successful run built after v0.2 changes).
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
9. Telegram: save the BotFather token in admin Settings, then connect each user via the one-time /start code. Alerts are sent only for AI-approved matching jobs.

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
- All matching recommendations must satisfy role, place, freshness and OpenCode's strict AI review. A score is **not** an employment probability.
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
