# JobHuntAI — V1 self-hosted job hunter

Native Android client + Windows Python engine. **The tool finds and evaluates jobs; it never submits applications.** Source code, tests, and APK builds are available in this repository.

## What is implemented

- Windows FastAPI + SQLite server, auto-generated long random phone pairing key, 15-minute scheduled scans and manual scan/pause/resume
- Automatic OpenCode CLI startup (when installed) and available free-model selection with preference for free DeepSeek; no paid DeepSeek API key
- PDF/DOCX resume extraction, explicitly confirmed skills, AI analysis suggestions, strict AppSec/Pentest roles
- 14 built-in ATS board identifiers (Lever, Ashby and SmartRecruiters; custom Greenhouse boards supported), 65+ categorized Indian/India-relevant employers, plus 30+ job board and career portal search targets
- Public Bing RSS indexed search over a rotating batch of job-family/site queries, with HTML JobPosting parsing and freshness/expiry checks
- Actual source diagnostics and scan history, job deduplication, company preference learning, checks for listings withdrawn from successfully enumerated ATS boards, downtime recovery
- AI evidence-based scoring, missing skill insights, truthful user-reviewed outreach drafts
- Native Android control center: connect, scan/pause, resume upload, skills/locations/experience settings, AI diagnostics, details, save/relevance feedback, application link
- Firebase push workflow with durable queue and retry states (**Firebase must be configured before it sends actual phone alerts**)
- Private HTTPS access through Tailscale Serve, Android Keystore encrypted bearer token

### Important limitations and truth in reporting
The **source directory is a list of search targets**, not proof of live integration with every portal. An ATS board is only operational if its response appears as \`ok\` under \`GET /api/sources\`; search indexing can fail, omit jobs or be delayed. Only dated postings are eligible for 85%-threshold push; undated listings show up in the feed as date unverified. Displaying a currently listed ATS vacancy does not guarantee applications can still be submitted. The Google Custom Search JSON API closed to new registrations in 2026, so no universal keyless Google Jobs integration is claimed.

A successful CI build is **not** proof of end-to-end live delivery. The real Windows host, selected OpenCode model, Firebase service account, Android phone, Tailscale connection, and one end-to-end job alert still require verification on your devices.

## 1. Start on Windows

Prerequisites: Windows 10/11, Python 3.11+ (install from python.org), internet access. Install OpenCode CLI, configure a free model *that is available in your account*, and verify you can use it. Avoid paid model selection.

In PowerShell:
\`\`\`powershell
cd C:\
git clone https://github.com/Godf-Cyb3r-1/jobHuntAI.git
cd C:\jobHuntAI\backend
.\run_windows.bat
\`\`\`
Alternatively, download the GitHub repository ZIP, unzip, and double-click \`backend\run_windows.bat\`.

On the first run it creates \`.venv\`, installs backend requirements, optionally launches \`opencode serve --hostname 127.0.0.1 --port 4096\`, starts the API, and prints a **private pairing key**. The key is generated locally and stored in \`backend\.jobhunt-api-key\`. It is NOT a paid AI API key. Never share or commit it.

Open \`http://127.0.0.1:8765/health\` in your Windows browser; expect \`{"status":"ok","configured":true}\`. Local Swagger API docs are at \`http://127.0.0.1:8765/docs\`. Authenticated endpoints need \`Authorization: Bearer YOUR_PAIRING_KEY\`.

For non-default OpenCode servers, copy \`backend/.env.example\` to \`backend/.env\` and set \`JOBHUNT_OPENCODE_URL\`, optionally \`JOBHUNT_OPENCODE_PASSWORD\` (if your server uses one), and \`JOBHUNT_OPENCODE_MODEL=opencode/your-free-model\`. These are **local environment settings**, not purchased keys. The UI's **Check OpenCode** uses \`GET /api/ai/status\` and shows whether free models are advertised.

### Scan configuration
The default first scan looks back 30 days. Subsequent scans look back one day, expanding the window up to 30 days if Windows was offline. Scans are scheduled every 15 minutes and one scan starts when the backend starts. High-confidence alerts require a dated posting, a matching role, an AI-verified score of 85+ and configured push. When a source omits a genuine posting date, its job is intentionally unverified and not immediately alerted.

### Optional auto-start
From a PowerShell session as your Windows user:
\`\`\`powershell
cd C:\jobHuntAI\backend
.\install_autostart.ps1
\`\`\`
This registers an **at-logon** task in Task Scheduler. The laptop must remain powered on, awake and connected. It does not keep running when the PC sleeps or is turned off. \`uninstall_autostart.ps1\` removes it.

## 2. Remote phone access over private HTTPS (recommended)

Install Tailscale on **Windows and Android**, sign into the same private tailnet, and enable its HTTPS feature if asked. From Windows PowerShell:
\`\`\`powershell
cd C:\jobHuntAI\backend
.\setup_remote_tailscale.ps1
\`\`\`
It runs \`tailscale serve --bg 8765\` and displays a stable \`https://your-windows-host.your-tailnet.ts.net\` URL. Enter **that exact URL** (not the placeholder) plus your generated pairing key in the Android app. Tailscale must be running on the phone to access the backend. Do not expose port 8765 directly on the public internet.

## 3. Install the native Android APK

Go to the latest successful [Android APK workflow](https://github.com/Godf-Cyb3r-1/jobHuntAI/actions/workflows/android-apk.yml), open its **Artifacts** section and download \`jobhuntai-debug-apk\`. Extract and install \`app-debug.apk\` on Android 8.0+. This is a **debug APK** for personal verification, not a signed Play Store release.

In the app: paste the Tailscale HTTPS URL and pairing key, **Connect / Refresh**, upload PDF/DOCX resume (max 3 MB), tap **Analyze resume with OpenCode**, review suggested roles/skills (no automatic false claims), enter your actual years of experience and locations, **Save preferences**, then **Scan now**. The job feed shows match explanations and dates. Tap **Details**, **Save**, **Relevant**, **Dismiss**, **Draft** (opens a share chooser for review), or **Open application**.

## 4. Configure real phone push via Firebase

The APK compiles without Firebase configuration but **it will not receive push alerts until Firebase is configured and you rebuild it**. Follow [Android Firebase setup](android/README.md). Firebase client configuration fields are added as repository Actions secrets; the server requires Firebase service account credentials locally. Never upload a service account JSON or resume to this public repository.

Check \`GET /api/alerts\` and \`GET /api/scan/history\` to troubleshoot pending messages. Failed alerts can be requeued through authenticated \`POST /api/alerts/retry\`.

## 5. Verify it end to end

- [ ] Windows \`/health\` shows ok; latest \`/api/status\` has scan history
- [ ] \`/api/sources\` reports which ATS boards succeed and fail
- [ ] \`/api/ai/status\` reports reachable OpenCode and a working free model
- [ ] Android connects through a **private HTTPS URL**, retrieves feed
- [ ] Resume uploads, AI suggests evidence-backed roles/skills, you confirm
- [ ] Real dated AppSec/Pentest job is discovered and ranked
- [ ] Firebase configured debug APK registers a device; real 85%+ match delivers a push
- [ ] Job link points to a currently accepting application

## Source coverage

Initial ATS identifiers are preloaded. Source status is observable in the app. Additional supported boards can be added with \`PUT /api/feeds\`, types \`lever\`, \`greenhouse\`, \`ashby\`, \`smartrecruiters\`. The indexed discovery catalog includes major Indian IT companies, product companies, security firms and public job boards. Employer tiers are **illustrative discovery groups**, not an official ranking. No CAPTCHA bypass, account scraping, or automatic job submission is used.

## Running automated tests
\`\`\`powershell
cd C:\jobHuntAI
py -m pip install -r backend/requirements-dev.txt
$env:PYTHONPATH="backend"
py -m pytest -q backend/tests
\`\`\`
GitHub Actions runs these tests on every backend change and assembles an Android debug APK on Android changes.

## Security and privacy

Never commit \`backend/.env\`, \`backend/.jobhunt-api-key\`, \`backend/jobhunt.db\`, \`backend/opencode.log\`, your resume, Firebase service-account JSON, or device credentials. The Windows database stores extracted resume text locally; the selected OpenCode model provider may receive resume/job text when evaluating. The Android pairing key uses Android Keystore encryption. Protect the Windows host and private HTTPS network.
