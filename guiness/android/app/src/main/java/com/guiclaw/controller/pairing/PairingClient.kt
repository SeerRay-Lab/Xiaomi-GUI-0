package com.guiness.controller.pairing

import com.guiness.controller.util.AppLog
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json

/**
 * 手机端回拨 PC。失败的情况都抛字符串化后的 PairingError 给 UI 用。
 */
object PairingClient {

    private val json = Json { ignoreUnknownKeys = true }

    sealed class Result {
        data object Ok : Result()
        data class Failed(val reason: String) : Result()
    }

    /**
     * 向 PC 发 POST /pair。
     *
     * @param payload        扫码解出来的 PC 方信息
     * @param phoneIp        手机当前局域网 IP
     * @param phonePort      APP 自己开的 HTTP server 端口（一般 8765）
     * @param phoneToken     APP 的 6 位访问码
     * @param phoneName      设备展示名（android.os.Build.MODEL）
     * @param timeoutMs      超时时间，局域网默认 3s 足够
     */
    suspend fun pair(
        payload: PairingPayload,
        phoneIp: String,
        phonePort: Int,
        phoneToken: String,
        phoneName: String,
        timeoutMs: Long = 3_000,
    ): Result = withContext(Dispatchers.IO) {
        val req = PairRequest(
            v = PAYLOAD_VERSION,
            phoneIp = phoneIp,
            phonePort = phonePort,
            phoneToken = phoneToken,
            phoneName = phoneName,
            token = payload.token,
        )
        val body = json.encodeToString(PairRequest.serializer(), req)
        val url = "http://${payload.pcIp}:${payload.pcPort}/pair"
        AppLog.i("pair → $url (phone=$phoneIp:$phonePort)")

        val client = HttpClient(CIO)
        try {
            val resp = withTimeout(timeoutMs) {
                client.post(url) {
                    contentType(ContentType.Application.Json)
                    setBody(body)
                }
            }
            val text = resp.bodyAsText()
            if (resp.status == HttpStatusCode.OK) {
                AppLog.i("pair 成功: $text")
                Result.Ok
            } else {
                AppLog.w("pair 被拒: ${resp.status} $text")
                Result.Failed("PC 拒绝配对: ${resp.status.value}")
            }
        } catch (e: Throwable) {
            AppLog.w("pair 异常", e)
            Result.Failed(e.message ?: e.javaClass.simpleName)
        } finally {
            client.close()
        }
    }
}
