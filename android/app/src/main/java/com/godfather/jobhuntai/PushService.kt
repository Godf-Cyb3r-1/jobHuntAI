package com.godfather.jobhuntai

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class PushService:FirebaseMessagingService() {
    override fun onMessageReceived(message:RemoteMessage) {
        val title=message.notification?.title ?: message.data["title"] ?: "New job match"
        val body=message.notification?.body ?: message.data["body"] ?: "Open JobHuntAI"
        val manager=getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if(Build.VERSION.SDK_INT>=26) manager.createNotificationChannel(
            NotificationChannel("job_matches","Job matches",NotificationManager.IMPORTANCE_HIGH))
        val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification=NotificationCompat.Builder(this,"job_matches")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title).setContentText(body).setAutoCancel(true)
            .setContentIntent(open).setPriority(NotificationCompat.PRIORITY_HIGH).build()
        manager.notify(System.currentTimeMillis().toInt(),notification)
    }
    override fun onNewToken(token:String) {
        // Registration is retried when the user opens the client.
    }
}
