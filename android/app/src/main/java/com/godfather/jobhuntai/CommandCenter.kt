
package com.godfather.jobhuntai

import android.app.Activity
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private val Ocean = Color(0xFF55D6C2)
private val Blue = Color(0xFF8DAEFF)
private val WarningColor = Color(0xFFFFC978)
private val SurfaceDark = Color(0xFF101824)

private fun JSONObject.txt(key:String, fallback:String = "—"):String =
    optString(key).takeUnless { it.isNullOrBlank() || it == "null" } ?: fallback
private fun parseJobs(raw:String):List<JSONObject> {
    val a=JSONArray(raw)
    return (0 until a.length()).mapNotNull { a.optJSONObject(it) }
}
private fun localTracker(activity:Activity):JSONObject {
    val prefs=activity.getSharedPreferences("tracker_v1",0)
    return try { JSONObject(prefs.getString("entries","{}") ?: "{}") } catch(_:Exception) { JSONObject() }
}
private fun saveTracker(activity:Activity, data:JSONObject) {
    activity.getSharedPreferences("tracker_v1",0).edit().putString("entries",data.toString()).apply()
}
private val stages=listOf("Saved","Applied","Assessment","Interview","Offer","Rejected","Withdrawn")
private fun parsedTimestamp(value:String):Long {
    val v=value.trim()
    if(v.isBlank() || v=="null") return Long.MIN_VALUE
    return runCatching { Instant.parse(v).toEpochMilli() }.getOrNull()
        ?: runCatching { OffsetDateTime.parse(v).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { LocalDateTime.parse(v).toInstant(ZoneOffset.UTC).toEpochMilli() }.getOrNull()
        ?: runCatching { LocalDate.parse(v.take(10)).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli() }.getOrDefault(Long.MIN_VALUE)
}
private fun dateKey(job:JSONObject):Long = when(job.optString("date_basis")) {
    "publication_date" -> parsedTimestamp(job.optString("posted_at"))
    "creation_lower_bound" -> parsedTimestamp(job.optString("created_at"))
    else -> Long.MIN_VALUE
}
private fun freshnessRank(job:JSONObject):Int = when(job.optString("date_basis")) {
    "publication_date" -> if(dateKey(job)==Long.MIN_VALUE) 0 else 2
    "creation_lower_bound" -> if(dateKey(job)==Long.MIN_VALUE) 0 else 1
    else -> 0
}
private val newestFirst = compareByDescending<JSONObject> { freshnessRank(it) }
    .thenByDescending { dateKey(it) }
    .thenByDescending { it.optInt("score") }
private val highestMatchFirst = compareByDescending<JSONObject> { it.optInt("score") }
    .then(newestFirst)


@Composable
fun JobHuntScreen(activity:Activity) {
    val prefs=remember { activity.getSharedPreferences("jobhunt",0) }
    val secret=remember {
        TokenStore(activity).also { store ->
            val previous=prefs.getString("token",null)
            if(!previous.isNullOrBlank()) {
                runCatching { store.put(previous); prefs.edit().remove("token").apply() }
            }
        }
    }
    var tab by remember { mutableIntStateOf(0) }
    var advanced by remember { mutableStateOf(false) }
    var jobs by remember { mutableStateOf(emptyList<JSONObject>()) }
    var overview by remember { mutableStateOf(JSONObject()) }
    var history by remember { mutableStateOf(emptyList<JSONObject>()) }
    var sources by remember { mutableStateOf(JSONObject()) }
    var ai by remember { mutableStateOf(JSONObject()) }
    var loaded by remember { mutableStateOf(false) }
    var working by remember { mutableStateOf(false) }
    var busyAction by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var lastUpdated by remember { mutableStateOf("") }
    var tracker by remember { mutableStateOf(localTracker(activity)) }
    var selectedJob by remember { mutableStateOf<JSONObject?>(null) }
    var details by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf("All") }
    var sortBy by remember { mutableStateOf("Newest") }
    var trackStage by remember { mutableStateOf("All") }
    var editTrack by remember { mutableStateOf<JSONObject?>(null) }
    var trackNotes by remember { mutableStateOf("") }
    var trackValue by remember { mutableStateOf("Saved") }
    var trackDate by remember { mutableStateOf("") }
    var toast by remember { mutableStateOf("") }
    val scope=rememberCoroutineScope()
    LaunchedEffect(toast) { if(toast.isNotBlank()) { delay(3500); toast="" } }
    val ctx=LocalContext.current
    val server=prefs.getString("server","") ?: ""
    val token=secret.get()

    fun background(task:suspend (Api)->Unit) {
        if(working || busyAction) return
        busyAction=true
        scope.launch {
            try {
                if(server.isBlank() || token.isBlank()) throw Exception("Set your server connection in Settings")
                withContext(Dispatchers.IO) { task(Api(server.trim(),token.trim())) }
            } catch(e:Exception) { error=e.message ?: "Request failed" }
            finally { busyAction=false }
        }
    }
    fun refresh() {
        if(working) return
        if(server.isBlank() || token.isBlank()) {
            error="Connect to your Windows backend under Settings"
            loaded=true
            return
        }
        working=true
        scope.launch {
            try {
                val result=withContext(Dispatchers.IO) {
                    val api=Api(server.trim(),token.trim())
                    val s=JSONObject(api.request("/api/status"))
                    val j=parseJobs(api.request("/api/jobs?limit=200"))
                    val h=runCatching { parseJobs(api.request("/api/scan/history?limit=30")) }.getOrDefault(emptyList())
                    val a=runCatching { JSONObject(api.request("/api/ai/status")) }.getOrDefault(JSONObject())
                    val src=runCatching { JSONObject(api.request("/api/sources")) }.getOrDefault(JSONObject())
                    listOf(s,j,h,a,src)
                }
                overview=result[0] as JSONObject
                jobs=result[1] as List<JSONObject>
                history=result[2] as List<JSONObject>
                ai=result[3] as JSONObject
                sources=result[4] as JSONObject
                lastUpdated=java.text.SimpleDateFormat("HH:mm",java.util.Locale.getDefault()).format(java.util.Date())
                error=""
                loaded=true
            } catch(e:Exception) {
                error=e.message ?: "Cannot reach server"
                loaded=true
            } finally { working=false }
        }
    }
    LaunchedEffect(server,token,advanced) { if(!advanced) refresh() }
    if(advanced) {
        Column {
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(8.dp),verticalAlignment=Alignment.CenterVertically) {
                TextButton(onClick={advanced=false}) { Text("‹ Back to settings") }
                Spacer(Modifier.weight(1f))
                Text("Existing controls",style=MaterialTheme.typography.labelMedium)
            }
            Box(Modifier.weight(1f)) { LegacyJobHuntScreen(activity) }
        }
        return
    }
    val scheme=darkColorScheme(
        primary=Ocean, secondary=Blue, tertiary=WarningColor,
        background=Color(0xFF0A101B), surface=SurfaceDark,
        surfaceVariant=Color(0xFF1A2736),
        onBackground=Color(0xFFEAF0F8), onSurface=Color(0xFFEAF0F8),
        onSurfaceVariant=Color(0xFFB5C1CF)
    )
    MaterialTheme(colorScheme=scheme) {
        if(selectedJob!=null) {
            val j=selectedJob!!
            AlertDialog(
                onDismissRequest={selectedJob=null},
                title={Text(j.txt("title","Job details"))},
                text={
                    Column(Modifier.heightIn(max=470.dp).verticalScroll(rememberScrollState()),
                        verticalArrangement=Arrangement.spacedBy(10.dp)) {
                        Text(j.txt("company")+" • "+j.txt("location"),color=Blue)
                        Text(j.optInt("score").toString()+"% match")
                        Text(j.txt("insight","No AI insights available yet"))
                        if(details.isNotBlank()) Text(details)
                        else Text("Detailed description was not loaded.",color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                },
                confirmButton={
                    TextButton(onClick={
                        val url=j.optString("url")
                        if(url.startsWith("https://")) ctx.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(url)))
                    }) { Text("Apply on site ↗") }
                },
                dismissButton={TextButton(onClick={selectedJob=null}) { Text("Close") }}
            )
        }
        if(editTrack!=null) {
            val j=editTrack!!
            Dialog(onDismissRequest={editTrack=null}) {
                Surface(
                    modifier=Modifier.fillMaxWidth().heightIn(max=690.dp),
                    shape=RoundedCornerShape(26.dp),
                    color=Color(0xFF172431),
                    tonalElevation=8.dp
                ) {
                    Column(
                        modifier=Modifier.verticalScroll(rememberScrollState()).padding(20.dp),
                        verticalArrangement=Arrangement.spacedBy(13.dp)
                    ) {
                        Row(verticalAlignment=Alignment.CenterVertically) {
                            Text("APPLICATION TRACKER",color=Ocean,
                                style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,
                                modifier=Modifier.weight(1f),letterSpacing=1.2.sp)
                            TextButton(onClick={editTrack=null}) { Text("Close") }
                        }
                        Text(j.txt("title"),style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
                        Text(j.txt("company")+"  •  "+j.txt("location"),
                            color=MaterialTheme.colorScheme.onSurfaceVariant,
                            style=MaterialTheme.typography.bodySmall)
                        HorizontalDivider(color=Color(0xFF344454))
                        Text("Where are you in the process?",
                            fontWeight=FontWeight.SemiBold,style=MaterialTheme.typography.titleMedium)
                        Column(verticalArrangement=Arrangement.spacedBy(7.dp)) {
                            stages.forEachIndexed { index, state ->
                                val chosen=trackValue==state
                                val accent=when(state) {
                                    "Offer" -> Ocean
                                    "Rejected","Withdrawn" -> WarningColor
                                    else -> Blue
                                }
                                Surface(
                                    shape=RoundedCornerShape(14.dp),
                                    color=if(chosen) Color(0xFF253E4C) else Color(0xFF1E2C3B),
                                    border=BorderStroke(if(chosen) 1.5.dp else 0.5.dp,
                                        if(chosen) accent else Color(0xFF354351)),
                                    onClick={trackValue=state},
                                    modifier=Modifier.fillMaxWidth()
                                ) {
                                    Row(Modifier.padding(horizontal=14.dp,vertical=11.dp),
                                        verticalAlignment=Alignment.CenterVertically) {
                                        Text(if(chosen)"●" else "○",color=if(chosen)accent else Blue,
                                            modifier=Modifier.width(29.dp),fontSize=18.sp)
                                        Text(state,modifier=Modifier.weight(1f),
                                            fontWeight=if(chosen)FontWeight.Bold else FontWeight.Normal)
                                        if(chosen) Text("SELECTED",color=accent,
                                            style=MaterialTheme.typography.labelSmall)
                                    }
                                }
                            }
                        }
                        OutlinedTextField(value=trackDate,onValueChange={trackDate=it},
                            label={Text("Follow-up date (optional)")},
                            placeholder={Text("e.g., 2026-11-24")},
                            modifier=Modifier.fillMaxWidth(),singleLine=true,
                            shape=RoundedCornerShape(14.dp))
                        OutlinedTextField(value=trackNotes,onValueChange={trackNotes=it},
                            label={Text("Notes & next steps")},
                            placeholder={Text("Recruiter, assessment, interview details...")},
                            modifier=Modifier.fillMaxWidth(),minLines=3,maxLines=5,
                            shape=RoundedCornerShape(14.dp))
                        Button(
                            onClick={
                                val id=j.txt("id")
                                val entry=JSONObject().put("job",j).put("stage",trackValue)
                                    .put("notes",trackNotes).put("follow_up",trackDate)
                                    .put("updated",System.currentTimeMillis())
                                val copy=JSONObject(tracker.toString())
                                copy.put(id,entry)
                                tracker=copy
                                saveTracker(activity,copy)
                                editTrack=null
                                toast="✓ Application updated"
                            },
                            modifier=Modifier.fillMaxWidth().height(52.dp),
                            shape=RoundedCornerShape(14.dp)
                        ) { Text("Save application status",fontWeight=FontWeight.Bold) }
                        Text("Only on this phone · No automatic applications",
                            modifier=Modifier.fillMaxWidth(),
                            color=MaterialTheme.colorScheme.onSurfaceVariant,
                            style=MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
        Scaffold(
            topBar={
                Surface(tonalElevation=2.dp,modifier=Modifier.statusBarsPadding()) {
                    Row(Modifier.fillMaxWidth().padding(horizontal=18.dp, vertical=14.dp),
                        verticalAlignment=Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("JOBHUNT / AI",fontWeight=FontWeight.Bold,
                                style=MaterialTheme.typography.titleLarge,letterSpacing=1.1.sp)
                            Text("Career command center",style=MaterialTheme.typography.labelSmall,
                                color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        TextButton(onClick={refresh()},enabled=!working) {Text("↻ Refresh")}
                        TextButton(onClick={tab=4}) {Text("⚙",fontSize=24.sp)}
                    }
                }
            },
            bottomBar={
                NavigationBar(containerColor=SurfaceDark) {
                    listOf("Home","Jobs","Tracker","Activity").forEachIndexed { i,name ->
                        NavigationBarItem(selected=tab==i,onClick={tab=i},
                            icon={ Text(listOf("◫","⌕","▤","◷")[i],fontSize=22.sp) },
                            label={Text(name,fontSize=11.sp)},alwaysShowLabel=true)
                    }
                }
            }
        ) { pad ->
            Column(Modifier.fillMaxSize().padding(pad)) {
                if(working) LinearProgressIndicator(Modifier.fillMaxWidth())
                if(error.isNotBlank()) {
                    Surface(color=Color(0xFF48302D)) {
                        Row(Modifier.fillMaxWidth().padding(12.dp),verticalAlignment=Alignment.CenterVertically) {
                            Text(error,Modifier.weight(1f),fontSize=12.sp)
                            TextButton(onClick={error=""}) {Text("×")}
                        }
                    }
                }
                if(toast.isNotEmpty()) {
                    Text(toast,Modifier.fillMaxWidth().padding(horizontal=18.dp, vertical=7.dp),
                        color=Ocean,style=MaterialTheme.typography.labelMedium)
                }
                when(tab) {
                    0 -> LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(18.dp),
                        verticalArrangement=Arrangement.spacedBy(14.dp)) {
                        item {
                            Text("Overview",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold)
                            Text("Your automated job search at a glance",color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        item {
                            ElevatedCard(colors=CardDefaults.elevatedCardColors(containerColor=Color(0xFF162C34))) {
                                Column(Modifier.fillMaxWidth().padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                                    Row(verticalAlignment=Alignment.CenterVertically) {
                                        Text("●",color=if(error.isEmpty()&&loaded) Ocean else WarningColor)
                                        Spacer(Modifier.width(8.dp))
                                        Text(if(!loaded)"Connecting" else if(error.isNotBlank())"Connection unavailable"
                                            else if(overview.optBoolean("paused"))"Scanner paused" else "Automation connected",
                                            fontWeight=FontWeight.Bold,modifier=Modifier.weight(1f))
                                        Badge { Text(if(overview.optBoolean("paused"))"PAUSED" else if(error.isEmpty() && loaded)"ONLINE" else "OFFLINE") }
                                    }
                                    Text("15-minute schedule • 30-day initial window • 85% alert threshold",
                                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                    HorizontalDivider()
                                    Text("Last refreshed: "+(lastUpdated.ifBlank { "Not yet" }),
                                        style=MaterialTheme.typography.labelMedium)
                                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                        Button(onClick={background { it.request("/api/scan","POST") };toast="Scan request submitted; refresh to verify"},enabled=!busyAction) {Text("Run scan")}
                                        OutlinedButton(onClick={
                                            val path=if(overview.optBoolean("paused"))"/api/resume" else "/api/pause"
                                            background { api -> api.request(path,"POST") }
                                            toast="Scanner state change requested"
                                        },enabled=!busyAction) {Text(if(overview.optBoolean("paused"))"Resume" else "Pause")}
                                    }
                                }
                            }
                        }
                        item {
                            Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                                StatCard("Jobs discovered", if(loaded && error.isEmpty()) overview.optInt("jobs",jobs.size).toString() else "—",
                                    "All stored jobs",Modifier.weight(1f))
                                StatCard("Strong matches", if(loaded && error.isEmpty()) jobs.count{it.optInt("score")>=85 && it.optInt("model_verified")==1}.toString() else "—",
                                    "85%+ AI verified",Modifier.weight(1f))
                            }
                        }
                        item {
                            Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                                StatCard("AI analyzed",if(loaded && error.isEmpty()) jobs.count{it.optInt("model_verified")==1}.toString() else "—",
                                    "Verified in feed",Modifier.weight(1f))
                                StatCard("Tracked",tracker.length().toString(),
                                    "Local applications",Modifier.weight(1f))
                            }
                        }
                        item { SectionHeading("Latest automation", "View all", {tab=3}) }
                        item {
                            val item=history.firstOrNull()
                            InfoCard {
                                if(item==null) Text("No scan history available yet.")
                                else {
                                    Text(item.txt("status","Unknown scan state"),fontWeight=FontWeight.Bold)
                                    Text("Started: "+item.txt("started"),style=MaterialTheme.typography.bodySmall)
                                    Text("New jobs: "+item.optInt("found"),style=MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                        item { SectionHeading("AI intelligence","Inspect", {tab=3}) }
                        item {
                            InfoCard {
                                Row(verticalAlignment=Alignment.CenterVertically) {
                                    Text("◈",color=Ocean,fontSize=26.sp)
                                    Spacer(Modifier.width(12.dp))
                                    Column {
                                        Text(if(ai.optBoolean("reachable"))"OpenCode reachable" else "AI status unconfirmed",
                                            fontWeight=FontWeight.Bold)
                                        Text(ai.optJSONArray("free_models")?.length()?.toString()?.plus(" free models advertised")
                                            ?: "Model telemetry unavailable",
                                            color=MaterialTheme.colorScheme.onSurfaceVariant,
                                            style=MaterialTheme.typography.bodySmall)
                                    }
                                }
                            }
                        }
                        item { SectionHeading("Recommended matches","See jobs", {tab=1}) }
                        items(jobs.filter {it.optInt("score")>=85}.sortedWith(newestFirst).take(3)) { job ->
                            CompactJob(job,onOpen={ selectedJob=job; details=""
                                background { api -> val d=JSONObject(api.request("/api/jobs/"+job.txt("id"))); withContext(Dispatchers.Main){details=d.optString("description")} }
                            },onTrack={
                                editTrack=job;val item=tracker.optJSONObject(job.txt("id"))
                                trackValue=item?.optString("stage") ?: "Saved"
                                trackNotes=item?.optString("notes") ?: ""
                                trackDate=item?.optString("follow_up") ?: ""
                            })
                        }
                        if(jobs.isEmpty()) item {EmptyState("No jobs loaded","Connect to your Windows engine, then refresh the feed.")}
                    }
                    1 -> Column(Modifier.fillMaxSize()) {
                        Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                            Text("Explore jobs",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold)
                            OutlinedTextField(value=query,onValueChange={query=it},
                                modifier=Modifier.fillMaxWidth(),singleLine=true,label={Text("Search roles, companies, locations")})
                            Row(horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                                listOf("All","85%+","AI verified","Saved").forEach { option ->
                                    FilterChip(selected=filter==option,onClick={filter=option},label={Text(option,fontSize=11.sp)})
                                }
                            }
                        }
                        Row(
                            Modifier.fillMaxWidth().padding(horizontal=18.dp),
                            verticalAlignment=Alignment.CenterVertically
                        ) {
                            Text("Sort by",style=MaterialTheme.typography.labelMedium,
                                color=MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.width(10.dp))
                            listOf("Newest","Top match").forEach { option ->
                                FilterChip(
                                    selected=sortBy==option,onClick={sortBy=option},
                                    label={Text(option,fontSize=12.sp)},
                                    modifier=Modifier.padding(end=8.dp)
                                )
                            }
                        }
                        val result=jobs.filter { j ->
                            (query.isBlank() || (j.txt("title")+" "+j.txt("company")+" "+j.txt("location")).contains(query,true)) &&
                            when(filter) {
                                "85%+" -> j.optInt("score")>=85
                                "AI verified" -> j.optInt("model_verified")==1
                                "Saved" -> tracker.has(j.txt("id"))
                                else -> true
                            }
                        }.sortedWith(if(sortBy=="Newest") newestFirst else highestMatchFirst)
                        LazyColumn(contentPadding=PaddingValues(horizontal=18.dp, vertical=6.dp),
                            verticalArrangement=Arrangement.spacedBy(10.dp)) {
                            item {Text(result.size.toString()+" opportunities · "+(if(sortBy=="Newest")"Newest verified dates first" else "Highest score first"),color=MaterialTheme.colorScheme.onSurfaceVariant,
                                style=MaterialTheme.typography.labelMedium)}
                            items(result) { j ->
                                CompactJob(j,onOpen={
                                    selectedJob=j;details=""
                                    background { api -> val d=JSONObject(api.request("/api/jobs/"+j.txt("id"))); withContext(Dispatchers.Main){details=d.optString("description")} }
                                },onTrack={
                                    editTrack=j;val item=tracker.optJSONObject(j.txt("id"))
                                    trackValue=item?.optString("stage") ?: "Saved"
                                    trackNotes=item?.optString("notes") ?: ""
                                    trackDate=item?.optString("follow_up") ?: ""
                                })
                            }
                            if(result.isEmpty()) item {EmptyState("No matches","Try another search or refresh the job feed.")}
                        }
                    }
                    2 -> Column(Modifier.fillMaxSize()) {
                        val entries=tracker.keys().asSequence().toList().mapNotNull { key ->
                            tracker.optJSONObject(key)
                        }
                        val visible=entries.filter {
                            trackStage=="All" || it.optString("stage")==trackStage
                        }.sortedByDescending { it.optLong("updated",0L) }
                        Column(Modifier.padding(start=18.dp,end=18.dp,top=16.dp,bottom=5.dp),
                            verticalArrangement=Arrangement.spacedBy(12.dp)) {
                            Text("My applications",style=MaterialTheme.typography.headlineMedium,
                                fontWeight=FontWeight.Bold)
                            Text("Stay organized from saving a role to receiving an offer.",
                                style=MaterialTheme.typography.bodySmall,
                                color=MaterialTheme.colorScheme.onSurfaceVariant)
                            Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                                StatCard("In pipeline",entries.count {
                                    it.optString("stage")!="Rejected" &&
                                    it.optString("stage")!="Withdrawn" &&
                                    it.optString("stage")!="Offer"
                                }.toString(),"Active records",Modifier.weight(1f))
                                StatCard("Interviews",entries.count {
                                    it.optString("stage")=="Interview"
                                }.toString(),"At interview",Modifier.weight(1f))
                                StatCard("Offers",entries.count {
                                    it.optString("stage")=="Offer"
                                }.toString(),"Successes",Modifier.weight(1f))
                            }
                            Text("APPLICATION STAGES",fontWeight=FontWeight.Bold,
                                color=Ocean,style=MaterialTheme.typography.labelMedium,
                                letterSpacing=1.sp)
                            Row(Modifier.horizontalScroll(rememberScrollState()),
                                horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                (listOf("All")+stages).forEach { state ->
                                    FilterChip(
                                        selected=trackStage==state,onClick={trackStage=state},
                                        label={Text(state+" ("+
                                            (if(state=="All") entries.size else entries.count {
                                                it.optString("stage")==state
                                            })+")",fontSize=12.sp)}
                                    )
                                }
                            }
                        }
                        LazyColumn(
                            contentPadding=PaddingValues(start=18.dp,end=18.dp,top=8.dp,bottom=22.dp),
                            verticalArrangement=Arrangement.spacedBy(12.dp)
                        ) {
                            items(visible) { entry ->
                                val job=entry.optJSONObject("job") ?: JSONObject()
                                val stage=entry.optString("stage","Saved")
                                ElevatedCard(Modifier.fillMaxWidth(),
                                    shape=RoundedCornerShape(20.dp),
                                    colors=CardDefaults.elevatedCardColors(containerColor=Color(0xFF182532))) {
                                    Column(Modifier.padding(17.dp),
                                        verticalArrangement=Arrangement.spacedBy(10.dp)) {
                                        Row(verticalAlignment=Alignment.CenterVertically) {
                                            Surface(shape=RoundedCornerShape(12.dp),
                                                color=Color(0xFF293D4D)) {
                                                Text("▣",modifier=Modifier.padding(12.dp),
                                                    fontSize=21.sp,color=Ocean)
                                            }
                                            Spacer(Modifier.width(12.dp))
                                            Column(Modifier.weight(1f)) {
                                                Text(job.txt("title"),fontWeight=FontWeight.Bold,
                                                    style=MaterialTheme.typography.titleMedium,
                                                    maxLines=2,overflow=TextOverflow.Ellipsis)
                                                Text(job.txt("company"),
                                                    color=MaterialTheme.colorScheme.onSurfaceVariant,
                                                    style=MaterialTheme.typography.bodySmall)
                                            }
                                        }
                                        Row(verticalAlignment=Alignment.CenterVertically) {
                                            Surface(
                                                shape=RoundedCornerShape(20.dp),
                                                color=if(stage=="Offer")Color(0xFF174B41) else Color(0xFF2D3C53)
                                            ) {
                                                Text("● "+stage,modifier=Modifier.padding(horizontal=12.dp,vertical=7.dp),
                                                    color=if(stage=="Offer")Ocean else Blue,
                                                    style=MaterialTheme.typography.labelMedium,
                                                    fontWeight=FontWeight.Bold)
                                            }
                                            Spacer(Modifier.weight(1f))
                                            Text(job.optInt("score").toString()+"% fit",
                                                color=Ocean,style=MaterialTheme.typography.labelMedium)
                                        }
                                        if(stage in listOf("Saved","Applied","Assessment","Interview","Offer")) {
                                            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(4.dp)) {
                                                stages.take(5).forEachIndexed { index, s ->
                                                    val done=index<=stages.indexOf(stage)
                                                    Box(
                                                        Modifier.weight(1f).height(5.dp)
                                                            .background(if(done)Ocean else Color(0xFF364654),
                                                                RoundedCornerShape(4.dp))
                                                    )
                                                }
                                            }
                                        }
                                        if(entry.optString("follow_up").isNotBlank())
                                            Text("◷  Follow up: "+entry.optString("follow_up"),
                                                style=MaterialTheme.typography.bodySmall,color=WarningColor)
                                        if(entry.optString("notes").isNotBlank())
                                            Text(entry.optString("notes"),
                                                style=MaterialTheme.typography.bodySmall,
                                                color=MaterialTheme.colorScheme.onSurfaceVariant,
                                                maxLines=3,overflow=TextOverflow.Ellipsis)
                                        HorizontalDivider(color=Color(0xFF344454))
                                        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                            OutlinedButton(
                                                onClick={
                                                    editTrack=job;trackValue=stage
                                                    trackNotes=entry.optString("notes")
                                                    trackDate=entry.optString("follow_up")
                                                },modifier=Modifier.weight(1f)
                                            ) {Text("Update status")}
                                            val jobUrl=job.optString("url")
                                            OutlinedButton(
                                                onClick={
                                                    if(jobUrl.startsWith("https://"))
                                                        ctx.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(jobUrl)))
                                                },enabled=jobUrl.startsWith("https://"),
                                                modifier=Modifier.weight(1f)
                                            ) {Text("View job ↗")}
                                        }
                                    }
                                }
                            }
                            if(visible.isEmpty()) item {
                                EmptyState(
                                    if(entries.isEmpty())"Your journey starts here" else "No jobs in this stage",
                                    if(entries.isEmpty())"Find a job, tap Track, and update each step of your application journey."
                                    else "Choose another stage to see your saved applications."
                                )
                            }
                        }
                    }
                    3 -> LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(18.dp),
                        verticalArrangement=Arrangement.spacedBy(12.dp)) {
                        item {
                            Text("Engine activity",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold)
                            Text("Real scan history, source checks and AI health",
                                color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        item {
                            InfoCard {
                                Text("Scheduler",fontWeight=FontWeight.Bold)
                                Text(if(overview.optBoolean("paused"))"Paused" else if(error.isBlank()&&loaded)"Connected (15-minute configured interval)" else "Unknown / offline",
                                    color=if(error.isBlank()&&loaded)Ocean else WarningColor)
                                Text("Last refresh: "+lastUpdated.ifBlank { "Never" },style=MaterialTheme.typography.bodySmall)
                                Text("Exact next execution is shown only when reported by the backend.",
                                    style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        item {
                            InfoCard {
                                Text("OpenCode / AI",fontWeight=FontWeight.Bold)
                                Text(if(ai.optBoolean("reachable"))"Reachable" else "Offline or status unavailable",
                                    color=if(ai.optBoolean("reachable"))Ocean else WarningColor)
                                Text((ai.optJSONArray("free_models")?.length() ?: 0).toString()+" advertised free models",
                                    style=MaterialTheme.typography.bodySmall)
                                Text("AI-verified jobs in current feed: "+jobs.count{it.optInt("model_verified")==1},
                                    style=MaterialTheme.typography.bodySmall)
                            }
                        }
                        item {
                            val h=sources.optJSONArray("source_health") ?: JSONArray()
                            val ok=(0 until h.length()).count {h.optJSONObject(it)?.optString("status")=="ok"}
                            val failed=(0 until h.length()).count {h.optJSONObject(it)?.optString("status")=="error"}
                            InfoCard {
                                Text("Job sources",fontWeight=FontWeight.Bold)
                                Text(ok.toString()+" healthy  •  "+failed+" failing",
                                    style=MaterialTheme.typography.bodyMedium)
                                Text(sources.optInt("catalog_size").toString()+" companies in discovery catalog",
                                    style=MaterialTheme.typography.bodySmall)
                            }
                        }
                        item { Text("Recent executions",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold) }
                        items(history) { h ->
                            InfoCard {
                                Row(verticalAlignment=Alignment.CenterVertically) {
                                    Text("●",color=if(h.optString("status").contains("fail",true))WarningColor else Ocean)
                                    Spacer(Modifier.width(8.dp))
                                    Text(h.txt("status","Scan"),fontWeight=FontWeight.Bold)
                                }
                                Text("Started: "+h.txt("started"),style=MaterialTheme.typography.bodySmall)
                                Text("Found: "+h.optInt("found")+" • Execution details depend on server telemetry",
                                    style=MaterialTheme.typography.bodySmall)
                            }
                        }
                        if(history.isEmpty()) item {EmptyState("No execution records","Scan history is unavailable or no scan has run yet.")}
                    }
                    4 -> LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(18.dp),
                        verticalArrangement=Arrangement.spacedBy(14.dp)) {
                        item {
                            Text("Settings",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold)
                            Text("Configuration is kept separate from your daily dashboard.",
                                color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        item {
                            InfoCard {
                                Text("Backend connection",fontWeight=FontWeight.Bold)
                                Text(if(server.isBlank())"Not configured" else server,
                                    style=MaterialTheme.typography.bodySmall)
                                Text(if(error.isEmpty()&&loaded)"Latest request succeeded" else "Connection not verified",
                                    color=if(error.isEmpty()&&loaded)Ocean else WarningColor,
                                    style=MaterialTheme.typography.labelMedium)
                                Button(onClick={advanced=true}) {Text("Configure server & pairing key")}
                            }
                        }
                        item {
                            InfoCard {
                                Text("Profile & resume",fontWeight=FontWeight.Bold)
                                Text("Allowed roles, verified skills, locations, priority companies, resume upload and analysis",
                                    style=MaterialTheme.typography.bodySmall)
                                OutlinedButton(onClick={advanced=true}) {Text("Manage profile")}
                            }
                        }
                        item {
                            InfoCard {
                                Text("Automation & AI",fontWeight=FontWeight.Bold)
                                Text("Initial freshness: 30 days • Recurring scan: 15 minutes",
                                    style=MaterialTheme.typography.bodySmall)
                                Text("Strict role family: On • Notification threshold: 85%",
                                    style=MaterialTheme.typography.bodySmall)
                                OutlinedButton(onClick={advanced=true}) {Text("Advanced scanner controls")}
                            }
                        }
                        item {
                            InfoCard {
                                Text("Notifications",fontWeight=FontWeight.Bold)
                                Text("Android push via Firebase, when configured on client and Windows host.",
                                    style=MaterialTheme.typography.bodySmall)
                                OutlinedButton(onClick={
                                    background { it.request("/api/notifications/test","POST") }
                                    toast="Test request submitted; verify delivery on your phone"
                                },enabled=!busyAction) {Text("Send test push")}
                            }
                        }
                        item {
                            InfoCard {
                                Text("Privacy & local tracker",fontWeight=FontWeight.Bold)
                                Text(tracker.length().toString()+" locally stored application records",
                                    style=MaterialTheme.typography.bodySmall)
                                Text("These records are private to this app installation, not synchronized to Windows.",
                                    style=MaterialTheme.typography.bodySmall)
                            }
                        }
                        item {Text("Client UI redesign • Windows backend unchanged",
                            style=MaterialTheme.typography.labelSmall,
                            color=MaterialTheme.colorScheme.onSurfaceVariant)}
                    }
                }
            }
        }
    }
}

@Composable private fun StatCard(title:String,value:String,sub:String,modifier:Modifier=Modifier) {
    ElevatedCard(modifier=modifier) {
        Column(Modifier.padding(15.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Text(value,style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold,color=Ocean)
            Text(title,style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.SemiBold)
            Text(sub,style=MaterialTheme.typography.labelSmall,
                color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=2)
        }
    }
}
@Composable private fun InfoCard(content:@Composable ColumnScope.()->Unit) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement=Arrangement.spacedBy(7.dp),content=content)
    }
}
@Composable private fun SectionHeading(title:String,link:String,action:()->Unit) {
    Row(verticalAlignment=Alignment.CenterVertically,modifier=Modifier.fillMaxWidth()) {
        Text(title,style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold,modifier=Modifier.weight(1f))
        TextButton(onClick=action) {Text(link+" →")}
    }
}
@Composable private fun EmptyState(title:String,body:String) {
    Column(Modifier.fillMaxWidth().padding(vertical=32.dp,horizontal=18.dp),
        horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(7.dp)) {
        Text("◌",fontSize=40.sp,color=Ocean)
        Text(title,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold)
        Text(body,style=MaterialTheme.typography.bodySmall,
            color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
@Composable private fun CompactJob(j:JSONObject,onOpen:()->Unit,onTrack:()->Unit) {
    val score=j.optInt("score")
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(15.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) {
                Text(j.txt("title"),style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold,
                    modifier=Modifier.weight(1f),maxLines=2,overflow=TextOverflow.Ellipsis)
                Spacer(Modifier.width(8.dp))
                Text(score.toString()+"%",color=if(score>=85)Ocean else Blue,
                    fontWeight=FontWeight.Bold)
            }
            Text(j.txt("company")+" • "+j.txt("location"),
                style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Text(j.txt("insight","No analysis available"),
                style=MaterialTheme.typography.bodySmall,maxLines=2,overflow=TextOverflow.Ellipsis)
            Text(if(j.optInt("model_verified")==1)"✓ AI evaluated" else "◇ AI not verified",
                style=MaterialTheme.typography.labelSmall,color=if(j.optInt("model_verified")==1)Ocean else WarningColor)
            Text(when(j.optString("date_basis")) {
                "publication_date" -> "Published: "+j.txt("posted_at")
                "creation_lower_bound" -> "Created: "+j.txt("created_at")+" • Publication unverified"
                else -> "Publication date unverified"
            },style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick=onOpen,modifier=Modifier.weight(1f)) {Text("Details")}
                Button(onClick=onTrack,modifier=Modifier.weight(1f)) {Text("Track")}
            }
        }
    }
}
