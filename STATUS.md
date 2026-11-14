# JobHuntAI V1 — verification handoff (2026-11-14)

**Code status:** V1 core feature paths implemented; live installation and push delivery NOT yet verified on the user's devices. No automatic job applications. V2 resume rewriting remains intentionally deferred.

## Automated checks

- [x] [Backend tests](https://github.com/Godf-Cyb3r-1/jobHuntAI/actions/workflows/backend-tests.yml) — passed on commit `b3e6367e`
- [x] [Android APK compilation](https://github.com/Godf-Cyb3r-1/jobHuntAI/actions/workflows/android-apk.yml) — latest source APK build passed
- [x] [Live ATS source smoke](https://github.com/Godf-Cyb3r-1/jobHuntAI/actions/workflows/source-smoke.yml) — 22 current seed boards returned successful responses in the preceding run; source content and job counts fluctuate
- [x] Deterministic end-to-end scanner integration test (discovery → filtering → AI mock → database → notification queue)
- [x] Unit tests for role exclusions, freshness, source closure, retry state, resume skill evidence, SmartRecruiters adapter, and API authentication

## Implemented in code

- [x] Native Android Kotlin/Compose APK; device-private Android Keystore pairing secret
- [x] Windows FastAPI server with random stable pairing key, SQLite persistent jobs and history
- [x] Windows startup helper, optional OpenCode auto-launch, logon task installer
- [x] 15-minute scheduler; initial 30 days; normal 1-day searches; downtime recovery up to 30 days
- [x] Strict explicitly selected role families, optional experience years, India/remote eligibility checks, user-prioritized companies
- [x] 22 source ATS board identifiers (Lever, Ashby, Greenhouse, SmartRecruiters) with live-checkable source status
- [x] Public indexed search with combined-role queries across broad company/ATS/Workday domains; public Bing RSS
- [x] Posting URL dedup, salary if disclosed, metadata/expiration checks, publication-date versus creation-date distinction
- [x] Source-health reporting and removal of vacancies missing from successfully refreshed ATS feeds
- [x] PDF/DOCX resume extraction; AI skill and role suggestions requiring user approval
- [x] OpenCode free-model discovery with DeepSeek preference, conservative fallback (no invented high match when AI fails)
- [x] AI match explanations, skill gaps, feedback-based adjustments, saved and dismissed jobs, truth-constrained cold outreach drafts
- [x] Firebase HTTP v1 sender, queue/retries, explicit test notification API and Android button
- [x] Private HTTPS helper using Tailscale Serve

## Needs verification/configuration outside GitHub

- [ ] On Windows, install Python and OpenCode; start `backend/run_windows.bat`; confirm `/health` and `/api/ai/status`
- [ ] Confirm the user's actual free OpenCode DeepSeek model responds to a real resume/job evaluation; provider quota may change
- [ ] Install Tailscale on Windows and Android; run `backend/setup_remote_tailscale.ps1`; pair APK via stable HTTPS URL
- [ ] Upload actual PDF/DOCX, verify extracted skill suggestions, edit allowed roles/years/locations, save preferences
- [ ] Inspect live job results and source failures in Android; validate application pages, geographical eligibility, dates and matches
- [ ] Create/configure Firebase project and four client build secrets; rebuild APK and install it
- [ ] Add backend Firebase service-account JSON **locally only**, restart, register Android device, press **Send test notification**
- [ ] Confirm a real newly discovered, freshness-verified and AI-scored 85%+ job generates a notification
- [ ] Validate continuous scanning after Windows restart; ensure the laptop remains awake and online

## Limitations that must not be represented as completed

- Authenticated LinkedIn/Naukri/Indeed data access is **not** implemented; public indexed discovery is best-effort, not full access to those portals.
- No universal keyless Google Jobs ingestion. Google Custom Search JSON API has been closed to new customers since 2026; do not claim comprehensive Google discovery.
- Search indexes can lag. Not all target company career portals have dedicated APIs; 22 ATS feeds reachable does not mean every company has relevant India jobs today.
- An ATS listing and reachable application page do not guarantee applications remain open; application acceptance should be checked before applying.
- Firebase push requires the user's Firebase project and phone; CI cannot demonstrate real-device delivery without those credentials.
- Windows cannot search while asleep/offline; recovery scans on restart do not recreate continuous 24/7 execution.
- No resume tailoring, DOCX modification or LaTeX resume generation in V1 (explicitly planned for V2).

## Install / verify

See [README](README.md) and [Android Firebase setup](android/README.md). Download the latest successful APK from [GitHub Actions](https://github.com/Godf-Cyb3r-1/jobHuntAI/actions/workflows/android-apk.yml) → Artifacts → `jobhuntai-debug-apk`.
