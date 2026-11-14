plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}
fun config(name:String) = (providers.gradleProperty(name).orNull ?: System.getenv(name) ?: "").replace("\\","\\\\").replace("\"","\\\"")
android {
    namespace = "com.godfather.jobhuntai"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.godfather.jobhuntai"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String","FCM_APP_ID","\""+config("FCM_APP_ID")+"\"")
        buildConfigField("String","FCM_API_KEY","\""+config("FCM_API_KEY")+"\"")
        buildConfigField("String","FCM_SENDER_ID","\""+config("FCM_SENDER_ID")+"\"")
        buildConfigField("String","FCM_PROJECT_ID","\""+config("FCM_PROJECT_ID")+"\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.00"))
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.firebase:firebase-messaging:24.1.0")
}
