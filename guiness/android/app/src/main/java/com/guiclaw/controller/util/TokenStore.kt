package com.guiness.controller.util

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.SecureRandom

/**
 * 对外暴露的访问令牌。走 EncryptedSharedPreferences，避免明文落盘。
 *
 * 单 token 模型：6 位数字验证码（类似向日葵）；首次启动随机生成，以后保持不变；
 * 用户点"重置 Token"可重生。WiFi backend 每次请求带 `X-Guiness-Token`。
 */
class TokenStore private constructor(private val prefs: SharedPreferences) {

    fun current(): String {
        val t = prefs.getString(KEY_TOKEN, null)
        if (!t.isNullOrBlank() && t.length == TOKEN_LENGTH && t.all { it.isDigit() }) return t
        return regenerate()
    }

    fun regenerate(): String {
        val rng = SecureRandom()
        val sb = StringBuilder(TOKEN_LENGTH)
        repeat(TOKEN_LENGTH) { sb.append(rng.nextInt(10)) }
        val code = sb.toString()
        prefs.edit().putString(KEY_TOKEN, code).apply()
        return code
    }

    companion object {
        private const val KEY_TOKEN = "auth_token"
        private const val PREFS_NAME = "guiness_secure"
        private const val TOKEN_LENGTH = 6

        @Volatile
        private var INSTANCE: TokenStore? = null

        fun get(ctx: Context): TokenStore {
            INSTANCE?.let { return it }
            synchronized(this) {
                INSTANCE?.let { return it }
                val prefs = buildPrefs(ctx.applicationContext)
                return TokenStore(prefs).also { INSTANCE = it }
            }
        }

        private fun buildPrefs(ctx: Context): SharedPreferences {
            return try {
                val key = MasterKey.Builder(ctx)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()
                EncryptedSharedPreferences.create(
                    ctx,
                    PREFS_NAME,
                    key,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
                )
            } catch (e: Exception) {
                // Keystore 异常时降级到普通 prefs（MVP 容错；日志提示）
                AppLog.w("加密 prefs 不可用，降级为明文", e)
                ctx.getSharedPreferences("${PREFS_NAME}_plain", Context.MODE_PRIVATE)
            }
        }
    }
}
