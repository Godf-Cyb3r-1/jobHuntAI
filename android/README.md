# Native Android APK

Android Studio: open this folder, sync Gradle and run `app`. CI workflow builds a debug APK and uploads it as a workflow artifact.

## Remote server
The Android app requires an **HTTPS** URL and a backend bearer token. Use a properly secured HTTPS tunnel or reverse proxy connected to your Windows backend. It deliberately refuses cleartext HTTP. Enter the URL/token in the app and use Connect / Refresh.

## Firebase push setup
The APK builds without Firebase configuration, but push **will not register** until configured. Create a Firebase Android project with package `com.godfather.jobhuntai`, then provide these four Firebase client configuration values via environment or Gradle project properties:
- `FCM_APP_ID`
- `FCM_API_KEY`
- `FCM_SENDER_ID`
- `FCM_PROJECT_ID`

For GitHub Actions, set matching repository Actions secrets. They are injected during compilation. The Firebase API key is an application identifier, not a service-account private key. Keep service-account credentials exclusively on the Windows backend; configure `JOBHUNT_FCM_PROJECT` and `JOBHUNT_FCM_TOKEN_FILE`, and install `google-auth`.

**Current caveat:** token refresh registration happens when the app opens; long-lived device-token handling and encrypted app token storage are future hardening items.

The server does not automatically discover ATS board IDs. Configure `/api/feeds` before expecting jobs.
