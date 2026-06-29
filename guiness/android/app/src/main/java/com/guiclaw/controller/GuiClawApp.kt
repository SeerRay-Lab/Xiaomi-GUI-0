package com.guiness.controller

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.content.ContextCompat
import com.guiness.controller.capture.ScreenCaptureManager
import com.guiness.controller.input.InputDispatcher
import com.guiness.controller.server.ControlSession
import com.guiness.controller.server.HttpServer
import com.guiness.controller.service.ControlForegroundService
import com.guiness.controller.util.AppLog
import com.guiness.controller.util.TokenStore
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * 进程级单例持有：
 *  - ScreenCaptureManager：单 projection 复用，避免每次开 Activity 都弹授权
 *  - InputDispatcher：串行手势注入
 *  - HttpServer：CIO 引擎常驻
 *  - ServerState：供 UI 订阅（是否运行 + 端口 + token）
 *
 * 实际 start/stop 由 ControlForegroundService 驱动，App 只做 holder。
 */
class GuinessApp : Application() {

    lateinit var capture: ScreenCaptureManager
        private set

    lateinit var input: InputDispatcher
        private set

    lateinit var session: ControlSession
        private set

    lateinit var server: HttpServer
        private set

    val state = MutableStateFlow(ServerState())

    override fun onCreate() {
        super.onCreate()
        singleton = this
        ensureNotificationChannel()
        capture = ScreenCaptureManager(this)
        input = InputDispatcher()
        session = ControlSession(appContext = this, capture = capture, input = input)
        server = HttpServer(
            session = session,
            tokenProvider = { TokenStore.get(this).current() },
            onIdleTimeout = {
                try {
                    ContextCompat.startForegroundService(this, ControlForegroundService.stopIntent(this))
                } catch (t: Throwable) {
                    AppLog.w("idle 超时触发停服失败", t)
                }
            },
        )
        AppLog.i("App 初始化完成")
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                val ch = NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.notification_channel_name),
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = getString(R.string.notification_channel_desc)
                    setShowBadge(false)
                }
                nm.createNotificationChannel(ch)
            }
        }
    }

    data class ServerState(
        val running: Boolean = false,
        val port: Int = -1,
        val ip: String? = null,
    )

    companion object {
        const val CHANNEL_ID = "guiness_control"
        private lateinit var singleton: GuinessApp
        fun instance(): GuinessApp = singleton
    }
}
