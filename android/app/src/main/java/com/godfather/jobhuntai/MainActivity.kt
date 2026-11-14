package com.godfather.jobhuntai

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class Api(private val base:String, private val token:String) {
    private val http = OkHttpClient.Builder().callTimeout(65, TimeUnit.SECONDS).build()
    fun request(path:String,method:String="GET",payload:String?=null):String {
        if (!base.startsWith("https://")) throw IOException("Use an HTTPS server URL")
        val builder=Request.Builder().url(base.trimEnd('/')+path)
          .header("Authorization","Bearer "+token)
        val body=payload?.toRequestBody("application/json".toMediaType())
        if(method!="GET") builder.method(method,body ?: ByteArray(0).toRequestBody(null))
        http.newCall(builder.build()).execute().use { response ->
            val result=response.body?.string() ?: ""
            if(!response.isSuccessful) throw IOException("HTTP ${response.code}: "+result.take(200))
            return result
        }
    }
    fun upload(bytes:ByteArray,filename:String):String {
        if (!base.startsWith("https://")) throw IOException("Use an HTTPS server URL")
        val body=MultipartBody.Builder().setType(MultipartBody.FORM)
          .addFormDataPart("file",filename,bytes.toRequestBody("application/octet-stream".toMediaType()))
          .build()
        http.newCall(Request.Builder().url(base.trimEnd('/')+"/api/resume/upload")
          .header("Authorization","Bearer "+token).post(body).build()).execute().use { response ->
            val result=response.body?.string() ?: ""
            if(!response.isSuccessful) throw IOException("HTTP ${response.code}: "+result.take(200))
            return result
        }
    }
}
class MainActivity:ComponentActivity() {
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        if(Build.VERSION.SDK_INT>=33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),101)
        startFirebase()
        setContent { MaterialTheme { JobHuntScreen(this) } }
    }
    private fun startFirebase() {
        if(BuildConfig.FCM_APP_ID.isBlank() || BuildConfig.FCM_SENDER_ID.isBlank() ||
           BuildConfig.FCM_API_KEY.isBlank() || BuildConfig.FCM_PROJECT_ID.isBlank()) return
        if(FirebaseApp.getApps(this).isEmpty()) {
            val options=FirebaseOptions.Builder().setApplicationId(BuildConfig.FCM_APP_ID)
              .setApiKey(BuildConfig.FCM_API_KEY).setGcmSenderId(BuildConfig.FCM_SENDER_ID)
              .setProjectId(BuildConfig.FCM_PROJECT_ID).build()
            FirebaseApp.initializeApp(this,options)
        }
    }
}
@Composable fun JobHuntScreen(activity:Activity) {
    val prefs=remember { activity.getSharedPreferences("jobhunt",0) }
    var server by remember { mutableStateOf(prefs.getString("server","") ?: "") }
    var token by remember { mutableStateOf(prefs.getString("token","") ?: "") }
    var status by remember { mutableStateOf("Connect to your Windows server") }
    var jobs by remember { mutableStateOf(emptyList<JSONObject>()) }
    var roles by remember { mutableStateOf(prefs.getString("roles","Penetration Tester, Application Security Engineer") ?: "") }
    var skills by remember { mutableStateOf(prefs.getString("skills","") ?: "") }
    var paused by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val scope=rememberCoroutineScope()
    val ctx=LocalContext.current
    fun execute(label:String, action:suspend (Api)->Unit) {
        if(busy) return
        busy=true
        scope.launch {
            try {
                val api=Api(server.trim(),token.trim())
                withContext(Dispatchers.IO) { action(api) }
                status=label+" successful"
            } catch(e:Exception) { status=label+": "+(e.message ?: "error") }
            finally { busy=false }
        }
    }
    fun refresh() {
        execute("Refresh") { api ->
            val info=JSONObject(api.request("/api/status"))
            val data=JSONArray(api.request("/api/jobs?limit=200"))
            val list=ArrayList<JSONObject>()
            for(i in 0 until data.length()) list.add(data.getJSONObject(i))
            withContext(Dispatchers.Main) {
                jobs=list
                paused=info.optBoolean("paused")
                status="Server online · ${info.optInt("jobs")} jobs stored"
            }
        }
    }
    val filePicker=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if(uri!=null) execute("Resume upload") { api ->
            val bytes=ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: throw IOException("Cannot read file")
            if(bytes.size>3_000_000) throw IOException("Resume exceeds 3 MB")
            val mime=ctx.contentResolver.getType(uri)
            val name=if(mime=="application/pdf") "resume.pdf" else "resume.docx"
            api.upload(bytes,name)
        }
    }
    LaunchedEffect(server,token) {
        if(server.startsWith("https://") && token.isNotBlank() &&
           BuildConfig.FCM_APP_ID.isNotBlank() && FirebaseApp.getApps(ctx).isNotEmpty()) {
            FirebaseMessaging.getInstance().token.addOnSuccessListener { fcm ->
                if(fcm.isNotBlank()) scope.launch {
                    try {
                        withContext(Dispatchers.IO) {
                            Api(server,token).request("/api/device","POST",JSONObject().put("token",fcm).toString())
                        }
                    } catch(_:Exception) {}
                }
            }
        }
    }
    Scaffold(topBar={ Surface(tonalElevation=3.dp) {
        Text("JobHuntAI  ·  Control Center",modifier=Modifier.padding(20.dp),style=MaterialTheme.typography.titleLarge)
    }}) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(horizontal=16.dp)) {
            Text(status,style=MaterialTheme.typography.bodyMedium)
            if(busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            Spacer(Modifier.height(10.dp))
            LazyColumn(verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(bottom=28.dp)) {
                item {
                    OutlinedTextField(server,{server=it},label={Text("Windows server HTTPS URL")},
                        placeholder={Text("https://your-tunnel.example")},modifier=Modifier.fillMaxWidth(),singleLine=true)
                    OutlinedTextField(token,{token=it},label={Text("API bearer token")},
                        visualTransformation=PasswordVisualTransformation(),modifier=Modifier.fillMaxWidth(),singleLine=true)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        Button(onClick={
                            prefs.edit().putString("server",server.trim()).putString("token",token.trim()).apply()
                            refresh()
                        },enabled=!busy) { Text("Connect / Refresh") }
                        OutlinedButton(onClick={
                            token="";prefs.edit().remove("token").apply();jobs=emptyList();status="Disconnected"
                        }) {Text("Disconnect")}
                    }
                }
                item {
                    Text("Scanner",style=MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        Button(onClick={execute("Scan") { it.request("/api/scan","POST") }},enabled=!busy) {Text("Scan now")}
                        OutlinedButton(onClick={
                            val path=if(paused) "/api/resume" else "/api/pause"
                            execute("Scanner state") { api ->
                                api.request(path,"POST")
                                withContext(Dispatchers.Main) {paused=!paused}
                            }
                        },enabled=!busy) { Text(if(paused)"Resume" else "Pause") }
                    }
                    Text("30-day initial window · 15-minute scans · ≥85% push · strict role matching",
                        style=MaterialTheme.typography.bodySmall)
                }
                item {
                    HorizontalDivider()
                    Text("Profile",style=MaterialTheme.typography.titleMedium)
                    OutlinedTextField(roles,{roles=it},label={Text("Allowed roles (comma separated)")},modifier=Modifier.fillMaxWidth())
                    OutlinedTextField(skills,{skills=it},label={Text("Verified skills (comma separated)")},modifier=Modifier.fillMaxWidth())
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        Button(onClick={
                            execute("Save profile") { api ->
                                val roleValues=roles.split(",").map{it.trim()}.filter{it.isNotEmpty()}
                                val skillValues=skills.split(",").map{it.trim()}.filter{it.isNotEmpty()}
                                val profile=JSONObject(api.request("/api/profile"))
                                profile.put("roles",JSONArray(roleValues)); profile.put("skills",JSONArray(skillValues))
                                profile.put("strict",true);profile.put("initial_days",30);profile.put("alert_threshold",85)
                                api.request("/api/profile","PUT",profile.toString())
                                prefs.edit().putString("roles",roles).putString("skills",skills).apply()
                            }
                        },enabled=!busy){Text("Save preferences")}
                        OutlinedButton(onClick={filePicker.launch(arrayOf("application/pdf",
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))}) {
                            Text("Upload resume")
                        }
                    }
                }
                item {
                    HorizontalDivider()
                    Text("Discovered jobs (${jobs.size})",style=MaterialTheme.typography.titleMedium)
                }
                items(jobs) { job ->
                    ElevatedCard(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                            Text(job.optString("title"),style=MaterialTheme.typography.titleMedium)
                            Text(job.optString("company")+" · "+job.optString("location"))
                            Text("${job.optInt("score")}% match · "+
                                (if(job.isNull("posted_at")) "Posting date unverified" else job.optString("posted_at")))
                            Text(job.optString("insight"),style=MaterialTheme.typography.bodySmall)
                            TextButton(onClick={
                                val url=job.optString("url")
                                if(url.startsWith("https://")) ctx.startActivity(
                                    Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url)))
                            }) { Text("Open application") }
                        }
                    }
                }
            }
        }
    }
}
