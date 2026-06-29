package com.guiness.controller.capture

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.HandlerThread
import android.util.DisplayMetrics
import android.view.Display
import android.view.WindowManager
import com.guiness.controller.util.AppLog
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicReference

/**
 * MediaProjection 截屏包装。
 *
 * 生命周期：
 *  1. Activity 弹 system intent 要授权 → resultCode/data
 *  2. ForegroundService 启起来后（Android 10+ 强制顺序）调 [init]
 *  3. [captureJpeg] 拿最新一帧 → JPEG bytes
 *  4. [release] 销毁 projection + reader + virtual display
 *
 * 帧生产采用单生产者 + 共享缓存模型：
 *  - ImageReader.OnImageAvailableListener 在 handlerThread 上单线程消费 acquireLatestImage，
 *    产出的原始 ARGB 帧放进 [latestRaw]（只留最新一张）。
 *  - 所有 /screenshot、/stream 请求只从 [latestRaw] 读，然后各自按自己的 quality/scale
 *    编码 JPEG。这样两路消费者互不争抢 ImageReader 的 buffer。
 */
class ScreenCaptureManager(private val ctx: Context) {

    private val pm = ctx.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
    private val wm = ctx.getSystemService(Context.WINDOW_SERVICE) as WindowManager

    @Volatile private var projection: MediaProjection? = null
    @Volatile private var reader: ImageReader? = null
    @Volatile private var display: VirtualDisplay? = null
    private val handlerThread = HandlerThread("Guiness-Capture").apply { start() }
    private val handler = Handler(handlerThread.looper)

    @Volatile var width: Int = 0; private set
    @Volatile var height: Int = 0; private set
    @Volatile var densityDpi: Int = DisplayMetrics.DENSITY_DEFAULT; private set

    /** 最新一帧原始像素（已从 ImageReader 拷出）。多消费者并发读，每次编码各取所需的 quality/scale。 */
    private val latestRaw = AtomicReference<RawFrame?>(null)

    val isReady: Boolean get() = projection != null && reader != null

    /** Activity 拿到 result 之后调一次即可。ForegroundService 必须已在前台。 */
    @Synchronized
    fun init(resultCode: Int, data: Intent) {
        release()
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        width = metrics.widthPixels
        height = metrics.heightPixels
        densityDpi = metrics.densityDpi

        val proj = pm.getMediaProjection(resultCode, data) ?: run {
            AppLog.e("getMediaProjection 返回 null")
            return
        }
        proj.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                AppLog.w("MediaProjection onStop 回调")
                release()
            }
        }, handler)

        // maxImages=3：给生产者留足 buffer，避免监听回调来不及消费时 VirtualDisplay 被堵。
        val r = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 3)
        r.setOnImageAvailableListener({ ir ->
            // 回调始终在 handlerThread 上，单线程串行执行。
            val img = try { ir.acquireLatestImage() } catch (_: Throwable) { null } ?: return@setOnImageAvailableListener
            try {
                latestRaw.set(RawFrame.from(img))
            } catch (e: Throwable) {
                AppLog.w("读取帧失败", e)
            } finally {
                try { img.close() } catch (_: Throwable) {}
            }
        }, handler)

        val d = proj.createVirtualDisplay(
            "Guiness-Projection",
            width, height, densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            r.surface, null, handler,
        )
        projection = proj
        reader = r
        display = d
        AppLog.i("MediaProjection 就绪 ${width}x${height} @${densityDpi}dpi")
    }

    /**
     * 取最新一帧并编码为 JPEG。每个调用者独立编码，互不阻塞。
     * reader 未就绪或还没收到第一帧时返回 null。
     */
    fun captureJpeg(quality: Int = 60, scale: Float = 1f): ByteArray? {
        if (reader == null) return null
        val raw = latestRaw.get() ?: return null
        return try {
            raw.toJpeg(quality, scale)
        } catch (e: Exception) {
            AppLog.e("截图编码失败", e)
            null
        }
    }

    @Synchronized
    fun release() {
        try { reader?.setOnImageAvailableListener(null, null) } catch (_: Throwable) {}
        try { display?.release() } catch (_: Throwable) {}
        try { reader?.close() } catch (_: Throwable) {}
        try { projection?.stop() } catch (_: Throwable) {}
        display = null
        reader = null
        projection = null
        latestRaw.set(null)
    }

    fun shutdown() {
        release()
        handlerThread.quitSafely()
    }

    /**
     * 一帧已解包的原始 ARGB 像素。不可变，可安全被多个线程并发读。
     *
     * 为什么不直接缓存 JPEG：/stream 和 /screenshot 用不同的 quality/scale，缓存 JPEG
     * 意味着其中一路永远拿到对方参数的结果。存原始像素让每个消费者按自己参数编码。
     */
    private class RawFrame(
        val pixels: ByteArray,
        val width: Int,
        val height: Int,
        val rowStride: Int,
        val pixelStride: Int,
    ) {
        fun toJpeg(quality: Int, scale: Float): ByteArray {
            val rowPadding = rowStride - pixelStride * width
            val bmpWidth = width + rowPadding / pixelStride
            val bmp = Bitmap.createBitmap(bmpWidth, height, Bitmap.Config.ARGB_8888)
            bmp.copyPixelsFromBuffer(java.nio.ByteBuffer.wrap(pixels))

            val cropped = if (rowPadding == 0) bmp else Bitmap.createBitmap(bmp, 0, 0, width, height)
            if (cropped !== bmp) bmp.recycle()

            val scaled = if (scale > 0f && scale < 1f) {
                Bitmap.createScaledBitmap(cropped, (cropped.width * scale).toInt(), (cropped.height * scale).toInt(), true)
                    .also { if (it !== cropped) cropped.recycle() }
            } else cropped

            val baos = ByteArrayOutputStream(256 * 1024)
            scaled.compress(Bitmap.CompressFormat.JPEG, quality.coerceIn(1, 100), baos)
            if (scaled !== cropped) scaled.recycle() else cropped.recycle()
            return baos.toByteArray()
        }

        companion object {
            fun from(image: Image): RawFrame {
                val plane = image.planes[0]
                val buf = plane.buffer
                val bytes = ByteArray(buf.remaining())
                buf.get(bytes)
                return RawFrame(
                    pixels = bytes,
                    width = image.width,
                    height = image.height,
                    rowStride = plane.rowStride,
                    pixelStride = plane.pixelStride,
                )
            }
        }
    }

    companion object {
        fun newScreenCaptureIntent(ctx: Context): Intent {
            val pm = ctx.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            return pm.createScreenCaptureIntent()
        }

        fun realDisplay(ctx: Context): Display {
            val wm = ctx.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            @Suppress("DEPRECATION")
            return wm.defaultDisplay
        }
    }
}
