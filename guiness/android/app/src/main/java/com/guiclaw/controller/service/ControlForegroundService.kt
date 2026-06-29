package com.guiness.controller.service

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import com.guiness.controller.GuinessApp
import com.guiness.controller.MainActivity
import com.guiness.controller.R
import com.guiness.controller.util.AppLog
import com.guiness.controller.util.NetworkUtils
import com.guiness.controller.util.TokenStore

/**
 * 控制总服务。Android 10+ 要求 mediaProjection FGS 必须先 startForeground，
 * 之后才能调 MediaProjectionManager.getMediaProjection。
 *
 * Intent extras:
 *  - EXTRA_RESULT_CODE: Int  MediaProjection 授权 resultCode
 *  - EXTRA_RESULT_DATA: Intent  授权返回 data
 */
class ControlForegroundService : LifecycleService() {

    override fun onBind(intent: Intent): IBinder? {
        super.onBind(intent)
        return null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START
        when (action) {
            ACTION_START -> handleStart(intent)
            ACTION_STOP -> handleStop()
        }
        return START_NOT_STICKY
    }

    private fun handleStart(intent: Intent?) {
        startForegroundWithNotification()

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, 0) ?: 0
        val data: Intent? = intent?.getParcelableExtra(EXTRA_RESULT_DATA)
        val app = GuinessApp.instance()

        if (resultCode != 0 && data != null) {
            app.capture.init(resultCode, data)
        } else {
            AppLog.w("ControlForegroundService 启动时未携带 MediaProjection 授权")
        }

        try {
            val port = app.server.start()
            val ip = NetworkUtils.preferredIpv4()
            app.state.value = GuinessApp.ServerState(running = true, port = port, ip = ip)
            AppLog.i("控制服务就绪 endpoint=http://${ip ?: "?"}:$port")
        } catch (e: Exception) {
            AppLog.e("启动 HTTP server 失败", e)
            app.state.value = GuinessApp.ServerState(running = false)
            stopSelf()
        }
    }

    private fun handleStop() {
        val app = GuinessApp.instance()
        try { app.server.stop() } catch (_: Throwable) {}
        try { app.capture.release() } catch (_: Throwable) {}
        // 断连 = 作废：轮换 Token，清空连接态，避免用户以为上次配对仍有效
        try { TokenStore.get(app).regenerate() } catch (t: Throwable) { AppLog.w("重置 Token 失败", t) }
        app.state.value = GuinessApp.ServerState(running = false)
        AppLog.i("控制服务停止，已轮换 Token")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun startForegroundWithNotification() {
        val tap = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val n: Notification = NotificationCompat.Builder(this, GuinessApp.CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText("远端控制器运行中")
            .setOngoing(true)
            .setContentIntent(tap)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID, n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
                    or ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }

    companion object {
        private const val NOTIF_ID = 1101
        const val ACTION_START = "com.guiness.controller.START"
        const val ACTION_STOP = "com.guiness.controller.STOP"
        const val EXTRA_RESULT_CODE = "resultCode"
        const val EXTRA_RESULT_DATA = "resultData"

        fun startIntent(ctx: Context, resultCode: Int, data: Intent): Intent {
            return Intent(ctx, ControlForegroundService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_RESULT_DATA, data)
            }
        }

        fun stopIntent(ctx: Context): Intent {
            return Intent(ctx, ControlForegroundService::class.java).apply { action = ACTION_STOP }
        }
    }
}
