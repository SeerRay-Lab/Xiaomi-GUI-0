package com.guiness.controller.server

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.util.DisplayMetrics
import android.view.WindowManager
import com.guiness.controller.util.AppLog
import com.guiness.controller.util.BackgroundLaunchPermission
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.call
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytes
import io.ktor.server.routing.Route
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.websocket.webSocket
import io.ktor.websocket.CloseReason
import io.ktor.websocket.Frame
import io.ktor.websocket.close
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/**
 * Stage 2 所有 HTTP 端点。字段命名与 server/Protocol.kt 对齐，和
 * Python `device/wifi_backend.py` 是协议耦合的——两边一起改。
 */
fun Route.registerControlRoutes(session: ControlSession) {
    // 统一使用真实屏幕尺寸（含导航栏/状态栏）。三个来源优先级：
    //   1. ScreenCaptureManager.width/height —— MediaProjection 已就绪时最权威，
    //      与截图分辨率完全一致
    //   2. WindowManager.defaultDisplay.getRealMetrics —— projection 未就绪时的回退
    //   3. Resources 旧路径 —— 上面两个都拿不到时兜底
    fun realMetrics(): Triple<Int, Int, Int> {
        val cw = session.capture.width
        val ch = session.capture.height
        val cdpi = session.capture.densityDpi
        if (cw > 0 && ch > 0) return Triple(cw, ch, cdpi)
        return try {
            val wm = session.appContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            val dm = DisplayMetrics()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealMetrics(dm)
            Triple(dm.widthPixels, dm.heightPixels, dm.densityDpi)
        } catch (_: Throwable) {
            val dm = session.appContext.resources.displayMetrics
            Triple(dm.widthPixels, dm.heightPixels, dm.densityDpi)
        }
    }

    get("/ping") {
        call.respond(Ok())
    }

    get("/device_info") {
        val (w, h, dpi) = realMetrics()
        call.respond(
            DeviceInfoResp(
                model = Build.MODEL ?: "unknown",
                osVersion = Build.VERSION.RELEASE ?: "unknown",
                sdk = Build.VERSION.SDK_INT,
                width = w,
                height = h,
                density = dpi,
                name = Build.MODEL ?: "unknown",
            )
        )
    }

    get("/permissions_status") {
        call.respond(
            PermissionsStatus(
                accessibility = session.a11y != null,
                mediaProjection = session.capture.isReady,
            )
        )
    }

    get("/screenshot") {
        val quality = call.request.queryParameters["q"]?.toIntOrNull() ?: 60
        val scale = call.request.queryParameters["scale"]?.toFloatOrNull() ?: 1f
        val bytes = session.capture.captureJpeg(quality = quality, scale = scale)
        if (bytes == null) {
            call.respond(
                HttpStatusCode.ServiceUnavailable,
                ErrorBody(code = "no_projection", msg = "media projection not ready"),
            )
        } else {
            call.respondBytes(bytes, ContentType.Image.JPEG)
        }
    }

    post("/tap") {
        val req = call.receive<TapReq>()
        requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        val (w, h, _) = realMetrics()
        val (x, y) = normalize(req.x, req.y, w, h)
        session.input.tap(x.toFloat(), y.toFloat())
        call.respond(Ok())
    }

    post("/long_press") {
        val req = call.receive<LongPressReq>()
        requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        val (w, h, _) = realMetrics()
        val (x, y) = normalize(req.x, req.y, w, h)
        session.input.longPress(x.toFloat(), y.toFloat(), req.durationMs.toLong())
        call.respond(Ok())
    }

    post("/swipe") {
        val req = call.receive<SwipeReq>()
        requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        val (w, h, _) = realMetrics()
        val (x1, y1) = normalize(req.x1, req.y1, w, h)
        val (x2, y2) = normalize(req.x2, req.y2, w, h)
        session.input.swipe(
            x1.toFloat(), y1.toFloat(), x2.toFloat(), y2.toFloat(),
            req.durationMs.toLong(),
        )
        call.respond(Ok())
    }

    post("/input_text") {
        val req = call.receive<InputTextReq>()
        val a11y = requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        // 如果指定了定位点，先点击激活 EditText
        req.position?.takeIf { it.size >= 2 }?.let { pos ->
            val (w, h, _) = realMetrics()
            val (x, y) = normalize(pos[0], pos[1], w, h)
            session.input.tap(x.toFloat(), y.toFloat())
            Thread.sleep(300)
        }
        val method = a11y.setText(req.text, clear = req.clear)
        if (req.enter) {
            Thread.sleep(200)
            a11y.pressKeyByName("ENTER")
        }
        call.respond(InputTextResp(method = method))
    }

    post("/key") {
        val req = call.receive<KeyReq>()
        val a11y = requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        a11y.pressKeyByName(req.key)
        call.respond(Ok())
    }

    post("/back") {
        val a11y = requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        a11y.back()
        call.respond(Ok())
    }

    post("/home") {
        val a11y = requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@post
        }
        a11y.home()
        call.respond(Ok())
    }

    get("/foreground") {
        val a11y = requireA11y(session) ?: run {
            call.respond(HttpStatusCode.ServiceUnavailable, a11yErr()); return@get
        }
        val (pkg, activity) = a11y.foregroundPackageAndActivity()
        call.respond(
            ForegroundResp(
                appName = pkg ?: "unknown",
                pkg = pkg,
                activity = activity,
            )
        )
    }

    post("/open") {
        val req = call.receive<OpenReq>()
        // Android 10+ 禁止从后台 context 启 Activity，但 AccessibilityService 是官方豁免
        // 对象。所以优先用 a11y Service 作为 Context；没有 a11y 时降级到 appContext
        // （只在前台时可用，多数调用场景下会失败）
        val ctx: Context = session.a11y ?: session.appContext
        val pm = session.appContext.packageManager
        val intent = pm.getLaunchIntentForPackage(req.pkg)
        if (intent == null) {
            call.respond(
                HttpStatusCode.NotFound,
                ErrorBody(code = "package_not_found", msg = "找不到可启动的包: ${req.pkg}"),
            )
            return@post
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        // MIUI/HyperOS 会在 startActivity 之后弹「启动应用」确认框；让 a11y 在接下来的
        // 几秒内自动点「始终允许」，否则 agent 侧会永远等那个 dialog
        session.a11y?.armAutoApproveLaunchDialog()
        try {
            ctx.startActivity(intent)
            call.respond(Ok())
        } catch (e: Exception) {
            AppLog.w("open 失败 pkg=${req.pkg}", e)
            val hint = if (!BackgroundLaunchPermission.isGranted(session.appContext)) {
                "未授予「后台弹出界面」权限（MIUIOP 10021），请在手机 APP 里点「去开启后台弹出」"
            } else {
                e.message ?: "start activity failed"
            }
            call.respond(
                HttpStatusCode.InternalServerError,
                ErrorBody(code = "open_failed", msg = hint),
            )
        }
    }

    post("/open_deeplink") {
        val req = call.receive<OpenDeeplinkReq>()
        val ctx: Context = session.a11y ?: session.appContext
        session.a11y?.armAutoApproveLaunchDialog()
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(req.uri)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            ctx.startActivity(intent)
            call.respond(Ok())
        } catch (e: Exception) {
            AppLog.w("open_deeplink 失败 uri=${req.uri}", e)
            val hint = if (!BackgroundLaunchPermission.isGranted(session.appContext)) {
                "未授予「后台弹出界面」权限（MIUIOP 10021），请在手机 APP 里点「去开启后台弹出」"
            } else {
                e.message ?: "deeplink error"
            }
            call.respond(
                HttpStatusCode.BadRequest,
                ErrorBody(code = "deeplink_failed", msg = hint),
            )
        }
    }

    post("/force_stop") {
        val req = call.receive<ForceStopReq>()
        // 非系统应用无法真正 forceStopPackage；用 killBackgroundProcesses 降级。
        val am = session.appContext.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val a11y = session.a11y
        try {
            am.killBackgroundProcesses(req.pkg)
            // 若 a11y 在线，且当前前台就是要停的包，顺手回 HOME 让它彻底退到后台
            if (a11y != null) {
                val fg = a11y.foregroundPackageAndActivity().first
                if (fg == req.pkg) a11y.home()
            }
            call.respond(ForceStopResp(ok = true, degraded = true, stopped = listOf(req.pkg)))
        } catch (e: Exception) {
            AppLog.w("force_stop 失败 pkg=${req.pkg}", e)
            call.respond(
                HttpStatusCode.InternalServerError,
                ErrorBody(code = "force_stop_failed", msg = e.message ?: "error"),
            )
        }
    }

    // Stage 4：WebSocket 截图流。
    // 和 `/screenshot` 共用 captureJpeg，但持续循环 + 只在成功时发帧。
    // 查询参数：
    //   fps   目标帧率（默认 12，上限 30；cap 太高会拖累 a11y 手势注入的主线程）
    //   q     JPEG 质量 1-100（默认 55；降帧率 + 降质量比降分辨率更划算）
    //   scale 0<scale<=1 的缩放倍数（默认 1.0 原分辨率）
    // 每帧以二进制 Frame 推；客户端收到什么解什么，无 JSON 包装
    webSocket("/stream") {
        val fps = (call.request.queryParameters["fps"]?.toIntOrNull() ?: 12).coerceIn(1, 30)
        val quality = (call.request.queryParameters["q"]?.toIntOrNull() ?: 55).coerceIn(1, 100)
        val scale = (call.request.queryParameters["scale"]?.toFloatOrNull() ?: 1f).coerceIn(0.1f, 1f)
        if (!session.capture.isReady) {
            close(CloseReason(CloseReason.Codes.TRY_AGAIN_LATER.code, "projection not ready"))
            return@webSocket
        }
        val periodMs = (1000L / fps).coerceAtLeast(16L)
        AppLog.i("stream 开始 fps=$fps q=$quality scale=$scale period=${periodMs}ms")
        try {
            while (isActive) {
                val frameStart = System.currentTimeMillis()
                val bytes = session.capture.captureJpeg(quality = quality, scale = scale)
                if (bytes != null) {
                    send(Frame.Binary(true, bytes))
                    // 每成功发一帧，stamp 一次活跃时间。否则 HttpServer 的 idle watchdog
                    // 只看 HTTP 请求的鉴权时间戳，会在 60s 后把正在直播的 stream 整服务杀掉
                    session.touchActivity()
                }
                val elapsed = System.currentTimeMillis() - frameStart
                val sleep = periodMs - elapsed
                if (sleep > 0) delay(sleep)
            }
        } catch (_: CancellationException) {
            // 正常关闭（客户端断或 server 被 stop）
        } catch (e: Throwable) {
            AppLog.w("stream 异常退出", e)
        } finally {
            // 注意：这里故意不再主动 stopIntent。/stream 断开可能只是 PC 网络抖动，
            // 停整个服务会导致 Token 被轮换、MediaProjection 被释放，必须重新扫码。
            // 真正的服务停止交给 idle watchdog 或用户手动操作
            AppLog.i("stream 退出（PC 断开或异常），服务继续运行")
        }
    }

    post("/force_stop_all") {
        val req = call.receive<ForceStopAllReq>()
        val am = session.appContext.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val skip = req.whitelist.toSet()
        val stopped = mutableListOf<String>()
        for (pkg in req.packages) {
            if (pkg in skip) continue
            try {
                am.killBackgroundProcesses(pkg)
                stopped.add(pkg)
            } catch (e: Exception) {
                AppLog.w("force_stop_all 单包失败 $pkg", e)
            }
        }
        session.a11y?.home()
        call.respond(ForceStopResp(ok = true, degraded = true, stopped = stopped))
    }
}

private fun requireA11y(session: ControlSession) = session.a11y?.also {
    // 命中即记一条 debug 友好日志
} ?: run {
    AppLog.w("无障碍服务未启用，拒绝请求")
    null
}

private fun a11yErr() = ErrorBody(code = "accessibility_disabled", msg = "无障碍服务未启用")

/**
 * 归一化坐标：[0,1.02] 按比例；否则视为像素。
 * 与 Python 侧 `device/_coord.py::normalize_point` 规则对齐。
 */
private fun normalize(x: Double, y: Double, w: Int, h: Int): Pair<Int, Int> {
    val px = if (x in 0.0..1.02) (w * x) else x
    val py = if (y in 0.0..1.02) (h * y) else y
    val ix = px.toInt().coerceIn(0, (w - 1).coerceAtLeast(0))
    val iy = py.toInt().coerceIn(0, (h - 1).coerceAtLeast(0))
    return ix to iy
}
