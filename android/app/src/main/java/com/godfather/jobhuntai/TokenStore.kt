package com.godfather.jobhuntai

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Device-private Android Keystore AES-GCM for the JobHuntAI bearer token. */
class TokenStore(private val context:Context) {
    private val alias="jobhuntai-device-pairing-v1"
    private val prefs=context.getSharedPreferences("jobhunt_secure",Context.MODE_PRIVATE)
    private fun key():SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore").apply {load(null)}
        val existing=store.getKey(alias,null) as? SecretKey
        if(existing!=null)return existing
        val generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(alias,
             KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
             .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
             .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
    fun put(value:String) {
        val cipher=Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE,key())
        val payload=cipher.iv+cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString("api_token",Base64.encodeToString(payload,Base64.NO_WRAP)).apply()
    }
    fun get():String {
        val encoded=prefs.getString("api_token",null) ?: return ""
        return try {
            val payload=Base64.decode(encoded,Base64.NO_WRAP)
            if(payload.size<29)return ""
            val cipher=Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,payload.copyOfRange(0,12)))
            String(cipher.doFinal(payload.copyOfRange(12,payload.size)),Charsets.UTF_8)
        } catch(_:Exception) {""}
    }
    fun clear() {prefs.edit().remove("api_token").apply()}
}
