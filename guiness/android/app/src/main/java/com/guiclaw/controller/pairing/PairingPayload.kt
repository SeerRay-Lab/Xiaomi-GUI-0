package com.guiness.controller.pairing

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * 与 PC 端 gui/pairing/payload.py 的字段一一对应（camelCase）。
 *
 *  二维码 → 手机：   PairingPayload
 *  手机 → /pair：    PairRequest
 *
 * 字段改动必须同步改 Python 侧，否则扫码/回拨任何一端会解析失败。
 */

const val PAYLOAD_VERSION = 1

@Serializable
data class PairingPayload(
    val v: Int,
    val pcIp: String,
    val pcPort: Int,
    val token: String,
    val pcName: String,
    val exp: Long,
) {
    /** 过期判断：扫码瞬间的本地时间 vs payload.exp（秒）。 */
    fun isExpired(nowSeconds: Long = System.currentTimeMillis() / 1000L): Boolean =
        nowSeconds > exp

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        /** 解析二维码文本。失败返回 null。 */
        fun parse(text: String): PairingPayload? = try {
            json.decodeFromString(serializer(), text)
        } catch (_: Throwable) {
            null
        }
    }
}

@Serializable
data class PairRequest(
    val v: Int,
    val phoneIp: String,
    val phonePort: Int,
    val phoneToken: String,
    val phoneName: String,
    val token: String,  // 回显 payload.token 给 PC 校验
)
