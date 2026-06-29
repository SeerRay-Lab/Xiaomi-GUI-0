package com.guiness.controller

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.guiness.controller.service.ControlAccessibilityService
import com.guiness.controller.service.ControlForegroundService
import com.guiness.controller.ui.AppRoot
import com.guiness.controller.ui.ScanActivity
import com.guiness.controller.ui.theme.GuinessTheme
import com.guiness.controller.util.AppLog
import com.guiness.controller.util.BackgroundLaunchPermission
import com.guiness.controller.util.NetworkUtils
import com.guiness.controller.util.TokenStore

class MainActivity : ComponentActivity() {

    private val projectionRequest = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            val intent = ControlForegroundService.startIntent(this, result.resultCode, result.data!!)
            ContextCompat.startForegroundService(this, intent)
        } else {
            AppLog.w("用户拒绝了 MediaProjection 授权")
        }
    }

    private val notificationPermRequest = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* 拒绝也能跑，只是通知看不到 */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ensureNotificationPermission()

        setContent {
            GuinessTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    val app = application as GuinessApp
                    val state by app.state.collectAsState()
                    val token = remember { mutableStateOf(TokenStore.get(this).current()) }
                    val ip = remember { mutableStateOf(NetworkUtils.preferredIpv4()) }
                    val a11yOn = remember { mutableStateOf(isAccessibilityOn()) }
                    val bgLaunchOn = remember { mutableStateOf(BackgroundLaunchPermission.isGranted(this)) }
                    val scope = rememberCoroutineScope()

                    // 服务停止后自动刷新 Token / IP 展示，避免残留上次连接信息
                    LaunchedEffect(state.running) {
                        if (!state.running) {
                            token.value = TokenStore.get(this@MainActivity).current()
                            ip.value = NetworkUtils.preferredIpv4()
                        }
                    }

                    AppRoot(
                        state = state,
                        token = token.value,
                        ip = ip.value,
                        accessibilityOn = a11yOn.value,
                        bgLaunchOn = bgLaunchOn.value,
                        onToggle = { if (state.running) stopServer() else startServer() },
                        onOpenAccessibilitySettings = { openAccessibilitySettings() },
                        onOpenBgLaunchSettings = { BackgroundLaunchPermission.openSettings(this) },
                        onRefresh = {
                            ip.value = NetworkUtils.preferredIpv4()
                            a11yOn.value = isAccessibilityOn()
                            bgLaunchOn.value = BackgroundLaunchPermission.isGranted(this)
                        },
                        onRegenerateToken = {
                            token.value = TokenStore.get(this).regenerate()
                        },
                        onCopy = { label, value -> copyToClipboard(label, value) },
                        onStartScan = {
                            startActivity(Intent(this, ScanActivity::class.java))
                        },
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // 从设置页回来时状态会变，forceCompose 由 MutableState 在下次 composition 自然刷新
    }

    private fun startServer() {
        if (!isAccessibilityOn()) {
            AppLog.w("请先开启无障碍服务")
            openAccessibilitySettings()
            return
        }
        val pm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projectionRequest.launch(pm.createScreenCaptureIntent())
    }

    private fun stopServer() {
        startService(ControlForegroundService.stopIntent(this))
    }

    private fun isAccessibilityOn(): Boolean {
        if (ControlAccessibilityService.current() != null) return true
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES)
            ?: return false
        val target = ComponentName(this, ControlAccessibilityService::class.java).flattenToString()
        return enabled.split(':').any { it.equals(target, ignoreCase = true) }
    }

    private fun openAccessibilitySettings() {
        try {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        } catch (e: Exception) {
            AppLog.e("打开无障碍设置失败", e)
        }
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                notificationPermRequest.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun copyToClipboard(label: String, value: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText(label, value))
        // Android 13+ 系统本身会弹自带气泡，但我们仍给个可靠的回执
        Toast.makeText(this, "已复制 $label", Toast.LENGTH_SHORT).show()
    }
}
