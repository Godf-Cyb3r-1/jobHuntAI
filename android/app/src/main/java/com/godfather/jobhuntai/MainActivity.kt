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
    val secretStore=remember {
        TokenStore(activity).also { secure ->
            val old=prefs.getString("token",null)
            if(!old.isNullOrBlank()) {
                try {secure.put(old);prefs.edit().remove("token").apply()}
                catch(_:Exception) {}
            }
        }
    }
    var token by remember { mutableStateOf(secretStore.get()) }
    var status by remember { mutableStateOf("Connect to your Windows server") }
    var jobs by remember { mutableStateOf(emptyList<JSONObject>()) }
    var sourceStatus by remember { mutableStateOf("") }
    var scanHistory by remember { mutableStateOf("") }
    var showDiagnostics by remember { mutableStateOf(false) }
    var roles by remember { mutableStateOf(prefs.getString("roles","Penetration Tester, Application Security Engineer") ?: "") }
    var skills by remember { mutableStateOf(prefs.getString("skills","") ?: "") }
    var locations by remember { mutableStateOf(prefs.getString("locations","India, Remote") ?: "India, Remote") }
    var yearsExperience by remember { mutableStateOf(prefs.getString("years","") ?: "") }
    var resumeSuggestions by remember { mutableStateOf(emptyList<String>()) }
    var roleSuggestions by remember { mutableStateOf(emptyList<String>()) }
    var resumeAnalysis by remember { mutableStateOf("") }
    var fullDetails by remember { mutableStateOf<String?>(null) }
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
            val result=JSONObject(api.upload(bytes,name))
            val candidates=result.optJSONArray("suggested_skills") ?: JSONArray()
            val list=(0 until candidates.length()).map { candidates.getString(it) }
            withContext(Dispatchers.Main) {resumeSuggestions=list}
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
    LaunchedEffect(Unit) {
        if(server.startsWith("https://") && token.isNotBlank())refresh()
    }
    if(fullDetails!=null) {
        AlertDialog(
            onDismissRequest={fullDetails=null},
            title={Text("Job details")},
            text={Column(Modifier.heightIn(max=470.dp).verticalScroll(rememberScrollState())) {
                Text(fullDetails ?: "")
            }},
            confirmButton={TextButton(onClick={fullDetails=null}){Text("Close")}}
        )
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
                            secretStore.put(token.trim())
                            prefs.edit().putString("server",server.trim()).apply()
                            refresh()
                        },enabled=!busy) { Text("Connect / Refresh") }
                        OutlinedButton(onClick={
                            token="";secretStore.clear();jobs=emptyList();status="Disconnected"
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
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick={
                            execute("Source status") { api ->
                                val info=JSONObject(api.request("/api/sources"))
                                val health=info.optJSONArray("source_health") ?: JSONArray()
                                val ok=(0 until health.length()).count {
                                    health.getJSONObject(it).optString("status")=="ok"
                                }
                                val errors=(0 until health.length()).count {
                                    health.getJSONObject(it).optString("status")=="error"
                                }
                                withContext(Dispatchers.Main) {
                                    sourceStatus="Sources: $ok healthy, $errors failing · "+
                                        info.optInt("catalog_size")+" catalog companies"
                                    showDiagnostics=true
                                }
                            }
                        },enabled=!busy){Text("Source health")}
                        OutlinedButton(onClick={
                            execute("Scan history") { api ->
                                val history=JSONArray(api.request("/api/scan/history?limit=5"))
                                val lines=(0 until history.length()).map {
                                    val h=history.getJSONObject(it)
                                    h.optString("status")+" · "+h.optInt("found")+" new · "+h.optString("started")
                                }
                                withContext(Dispatchers.Main) {
                                    scanHistory=lines.joinToString("\n")
                                    showDiagnostics=true
                                }
                            }
                        },enabled=!busy){Text("History")}
                    }
                    OutlinedButton(enabled=!busy,onClick={
                        execute("AI status") { api ->
                            val ai=JSONObject(api.request("/api/ai/status"))
                            val models=ai.optJSONArray("free_models")?.length() ?: 0
                            withContext(Dispatchers.Main) {
                                sourceStatus=(if(ai.optBoolean("reachable")) "OpenCode online"
                                    else "OpenCode offline")+" · $models advertised free models"
                                showDiagnostics=true
                            }
                        }
                    }) {Text("Check OpenCode")}
                    if(showDiagnostics) {
                        Text(sourceStatus,style=MaterialTheme.typography.bodySmall)
                        if(scanHistory.isNotEmpty()) Text(scanHistory,style=MaterialTheme.typography.bodySmall)
                    }
                    Text("30-day initial window · 15-minute scans · ≥85% push · strict role matching",
                        style=MaterialTheme.typography.bodySmall)
                }
                item {
                    HorizontalDivider()
                    Text("Profile",style=MaterialTheme.typography.titleMedium)
                    OutlinedTextField(roles,{roles=it},label={Text("Allowed roles (comma separated)")},modifier=Modifier.fillMaxWidth())
                    OutlinedTextField(skills,{skills=it},label={Text("Verified skills (comma separated)")},modifier=Modifier.fillMaxWidth())
                    OutlinedTextField(locations,{locations=it},label={Text("Preferred locations (comma separated)")},modifier=Modifier.fillMaxWidth())
                    OutlinedTextField(yearsExperience,{yearsExperience=it},
                        label={Text("Years of experience (optional)")},modifier=Modifier.fillMaxWidth())
                    OutlinedButton(enabled=!busy,onClick={
                        execute("Analyze resume") { api ->
                            val result=JSONObject(api.request("/api/resume/analyze"))
                            val skillArray=result.optJSONArray("suggested_skills") ?: JSONArray()
                            val rolesArray=result.optJSONArray("suggested_roles") ?: JSONArray()
                            withContext(Dispatchers.Main) {
                                resumeSuggestions=(0 until skillArray.length()).map {skillArray.getString(it)}
                                roleSuggestions=(0 until rolesArray.length()).map {rolesArray.getString(it)}
                                resumeAnalysis=result.optString("summary")
                            }
                        }
                    }){Text("Analyze resume with OpenCode")}
                    if(resumeAnalysis.isNotEmpty())Text(resumeAnalysis,style=MaterialTheme.typography.bodySmall)
                    if(roleSuggestions.isNotEmpty()) {
                        Text("Suggested roles: "+roleSuggestions.joinToString(", "),
                             style=MaterialTheme.typography.bodySmall)
                        OutlinedButton(onClick={roles=roleSuggestions.joinToString(", ")}) {
                            Text("Use suggested roles")
                        }
                    }
                    if(resumeSuggestions.isNotEmpty()) {
                        Text("Resume suggestions — confirm only skills you know: "+
                            resumeSuggestions.joinToString(", "),style=MaterialTheme.typography.bodySmall)
                        OutlinedButton(onClick={
                            val existing=skills.split(",").map{it.trim()}.filter{it.isNotEmpty()}
                            skills=(existing+resumeSuggestions).distinct().joinToString(", ")
                        }){Text("Use suggested skills")}
                    }
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        Button(onClick={
                            execute("Save profile") { api ->
                                val roleValues=roles.split(",").map{it.trim()}.filter{it.isNotEmpty()}
                                val skillValues=skills.split(",").map{it.trim()}.filter{it.isNotEmpty()}
                                val profile=JSONObject(api.request("/api/profile"))
                                profile.put("roles",JSONArray(roleValues)); profile.put("skills",JSONArray(skillValues))
                                val places=locations.split(",").map{it.trim()}.filter{it.isNotEmpty()}
                                profile.put("locations",JSONArray(places))
                                if(yearsExperience.toDoubleOrNull()!=null)
                                    profile.put("years_experience",yearsExperience.toDouble())
                                else profile.put("years_experience",JSONObject.NULL)
                                profile.put("strict",true);profile.put("initial_days",30);profile.put("alert_threshold",85)
                                api.request("/api/profile","PUT",profile.toString())
                                prefs.edit().putString("roles",roles).putString("skills",skills)
                                    .putString("locations",locations).putString("years",yearsExperience).apply()
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
                            Text(if(job.optInt("model_verified")==1) "AI evaluated"
                                 else "Fallback estimate (AI not verified)",
                                 style=MaterialTheme.typography.labelSmall)
                            Row(horizontalArrangement=Arrangement.spacedBy(5.dp)) {
                                TextButton(enabled=!busy,onClick={
                                    execute("Marked relevant") { api ->
                                        api.request("/api/jobs/"+job.optString("id")+"/feedback",
                                            "POST",JSONObject().put("value","relevant").toString())
                                    }
                                }){Text("Relevant")}
                                TextButton(enabled=!busy,onClick={
                                    execute("Dismiss") { api ->
                                        api.request("/api/jobs/"+job.optString("id")+"/feedback",
                                            "POST",JSONObject().put("value","dismiss").toString())
                                        withContext(Dispatchers.Main) {
                                            jobs=jobs.filter { it.optString("id")!=job.optString("id") }
                                        }
                                    }
                                }){Text("Dismiss")}
                            }
                            Row(horizontalArrangement=Arrangement.spacedBy(5.dp)) {
                                TextButton(enabled=!busy,onClick={
                                    execute("Job details") { api ->
                                        val full=JSONObject(api.request("/api/jobs/"+job.optString("id")))
                                        withContext(Dispatchers.Main) {
                                            fullDetails=full.optString("description","No description available")
                                        }
                                    }
                                }){Text("Details")}
                                TextButton(enabled=!busy,onClick={
                                    execute("Saved job") { api ->
                                        api.request("/api/jobs/"+job.optString("id")+"/save","POST")
                                    }
                                }){Text("Save")}
                                TextButton(enabled=!busy,onClick={
                                    execute("Outreach draft") { api ->
                                        val draft=JSONObject(api.request("/api/jobs/"+job.optString("id")+"/outreach"))
                                        val share=Intent(Intent.ACTION_SEND).apply {
                                            type="text/plain"
                                            putExtra(Intent.EXTRA_SUBJECT,draft.optString("subject"))
                                            putExtra(Intent.EXTRA_TEXT,draft.optString("body"))
                                        }
                                        withContext(Dispatchers.Main) {
                                            ctx.startActivity(Intent.createChooser(share,"Review outreach draft"))
                                        }
                                    }
                                }){Text("Draft")}
                            }
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
