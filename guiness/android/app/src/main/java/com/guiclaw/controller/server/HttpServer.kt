package com.guiness.controller.server

import com.guiness.controller.util.AppLog
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.install
import io.ktor.server.cio.CIO
import io.ktor.server.engine.ApplicationEngine
import io.ktor.server.engine.embeddedServer
import io.ktor.server.plugins.callloging.CallLogging
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.plugins.statuspages.StatusPages
import io.ktor.server.response.respond
import io.ktor.server.routing.routing
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.pingPeriod
import io.ktor.server.websocket.timeout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import java.io.IOException
import java.net.ServerSocket
import java.time.Duration

/**
 * 内嵌 Ktor HTTP server。选 CIO 引擎（协程、无 Netty 依赖）——Netty 在 Android
 * 上会引入 resource leak 工具链 + 额外 dex，不必要；CIO 够用。
 *
 * 端口：默认 8765，占用则向上探测到 8779。失败抛异常由调用方兜住。
 */
class HttpServer(
    private val session: ControlSession,
    private val tokenProvider: () -> String,
    private val onIdleTimeout: () -> Unit = {},
) {
    @Volatile private var engine: ApplicationEngine? = null
    @Volatile var port: Int = -1
        private set

    @Volatile private var lastActivityAtMs: Long = 0L
    private var watchdogScope: CoroutineScope? = null
    private var watchdogJob: Job? = null

    fun start(preferredPort: Int = DEFAULT_PORT): Int {
        if (engine != null) return port
        val actual = findAvailablePort(preferredPort)
        lastActivityAtMs = System.currentTimeMillis()
        // 把活跃心跳注入 session，供 /stream 每帧调用
        session.activityTicker = { lastActivityAtMs = System.currentTimeMillis() }
        val server = embeddedServer(CIO, port = actual, host = "0.0.0.0") {
            install(ContentNegotiation) {
                json(Json {
                    ignoreUnknownKeys = true
                    explicitNulls = false
                    encodeDefaults = true   // 必须：否则带默认值的 protocolVersion / ok 等字段不会出现在 JSON 里
                })
            }
            install(CallLogging)
            install(WebSockets) {
                // 5 秒 ping 防 NAT 空闲断连；30s 没回就踢掉。截图流是持续写入，客户端侧
                // 读到任何帧本身也算一次心跳，pingPeriod 主要给空闲连接保活
                pingPeriod = Duration.ofSeconds(5)
                timeout = Duration.ofSeconds(30)
                maxFrameSize = 4L * 1024 * 1024   // 单帧 JPEG 极端值约 2MB，4MB 保险
                masking = false
            }
            install(StatusPages) {
                exception<Throwable> { call, cause ->
                    AppLog.e("route ${call.request.local.uri} 异常", cause)
                    call.respond(
                        HttpStatusCode.InternalServerError,
                        ErrorBody(code = "server_error", msg = cause.message ?: cause.javaClass.simpleName),
                    )
                }
            }
            installGuinessAuth(
                expectedToken = tokenProvider,
                onAuthorized = { lastActivityAtMs = System.currentTimeMillis() },
            )
            routing { registerControlRoutes(session) }
        }
        server.start(wait = false)
        engine = server
        port = actual
        startIdleWatchdog()
        AppLog.i("HTTP server 启动: 0.0.0.0:$actual")
        return actual
    }

    fun stop() {
        stopIdleWatchdog()
        session.activityTicker = null
        engine?.let {
            try { it.stop(500, 1000) } catch (e: Exception) { AppLog.w("停 server 失败", e) }
        }
        engine = null
        port = -1
    }

    private fun startIdleWatchdog() {
        stopIdleWatchdog()
        val scope = CoroutineScope(Dispatchers.Default)
        watchdogScope = scope
        watchdogJob = scope.launch {
            while (isActive) {
                delay(CHECK_INTERVAL_MS)
                val idleMs = System.currentTimeMillis() - lastActivityAtMs
                if (idleMs >= IDLE_TIMEOUT_MS) {
                    AppLog.i("空闲 ${idleMs / 1000}s 未收到请求，自动停止服务")
                    try { onIdleTimeout() } catch (t: Throwable) { AppLog.w("onIdleTimeout 失败", t) }
                    break
                }
            }
        }
    }

    private fun stopIdleWatchdog() {
        try { watchdogJob?.cancel() } catch (_: Throwable) {}
        try { watchdogScope?.cancel() } catch (_: Throwable) {}
        watchdogJob = null
        watchdogScope = null
    }

    private fun findAvailablePort(start: Int): Int {
        for (p in start until start + PORT_RANGE) {
            try {
                ServerSocket(p).use { /* 立刻关闭，让 Ktor 去抢占 */ }
                return p
            } catch (_: IOException) {
                // 占用，继续探测
            }
        }
        throw IOException("无可用端口（$start..${start + PORT_RANGE - 1} 全部被占）")
    }

    companion object {
        const val DEFAULT_PORT = 8765
        const val PORT_RANGE = 15 // 8765..8779
        private const val CHECK_INTERVAL_MS = 10_000L
        private const val IDLE_TIMEOUT_MS = 60_000L
    }
}
