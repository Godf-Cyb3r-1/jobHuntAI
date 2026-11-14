# Native Android verification and Firebase push

## Build / install
[Android APK Actions workflow](https://github.com/Godf-Cyb3r-1/jobHuntAI/actions/workflows/android-apk.yml) produces `jobhuntai-debug-apk` ZIP containing `app-debug.apk`. Install on Android 8.0+, allow notification permission on Android 13+.

The app **refuses cleartext HTTP**. Install Tailscale on Windows and Android and connect through Tailscale Serve's stable HTTPS URL. The pairing key is generated on the Windows backend and stored encrypted with Android Keystore on the device.

## Firebase real-time push — required one-time setup

1. Open the [Firebase console](https://console.firebase.google.com/), create or select a project, enable Cloud Messaging and add an Android app with **package name** `com.godfather.jobhuntai`.
2. From the Firebase project settings (Android app and Cloud Messaging), collect the client values below and add these exact names to **GitHub repository → Settings → Secrets and variables → Actions → New repository secret**:
   - `FCM_APP_ID` (the Firebase app ID, typically `1:...:android:...`)
   - `FCM_API_KEY` (Firebase web/client configuration API key; not a paid model key)
   - `FCM_SENDER_ID` (Firebase messaging sender/project number)
   - `FCM_PROJECT_ID` (Firebase project ID)
3. Trigger a new **Android APK** workflow, download and install the new artifact. The APK only registers an FCM device token when **all four values** are present at compile time and the app connects.
4. On the **Windows host only**, obtain a Firebase service account with permission to send FCM HTTP v1 messages, save its JSON outside GitHub (for example `C:\jobHuntSecrets\fcm-service.json`), and set in `backend\.env`:
   ```text
   JOBHUNT_FCM_PROJECT=your-firebase-project-id
   JOBHUNT_FCM_TOKEN_FILE=C:\jobHuntSecrets\fcm-service.json
   ```
5. Restart the Windows backend, open the APK and tap **Connect / Refresh** once to register its FCM device token. Grant notification permission.
6. To test, first check `GET /api/alerts` for queued alerts and `GET /api/sources` for live discoveries. A push is attempted for *new*, date-verified, relevant jobs scoring at least 85% with actual OpenCode inference. Without a qualified new job, there may be no push to test. The server does not invent a qualifying job.

The app initializes Firebase programmatically from the four BuildConfig settings. **You do not need to commit `google-services.json` to GitHub**. Do not place service-account JSON in the Android app, Actions secrets used by the client, or any public repository path.

### Notes
The Firebase API key identifies the client project, and Firebase server authentication uses the private service account credential. They are **not OpenCode/DeepSeek API keys**. The Android app only stores the Windows pairing secret in Android Keystore; server URL, job preferences and notification token registration are separate. CI APK success alone does not demonstrate live FCM delivery.
