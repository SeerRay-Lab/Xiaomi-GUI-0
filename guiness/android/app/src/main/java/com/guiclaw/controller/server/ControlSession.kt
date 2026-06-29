package com.guiness.controller.server

import android.content.Context
import com.guiness.controller.capture.ScreenCaptureManager
import com.guiness.controller.input.InputDispatcher
import com.guiness.controller.service.ControlAccessibilityService

/**
 * 运行期能力聚合：被 Routes 注入使用。
 *
 * 为什么是 class 而不是单例：将来（Stage 4）切到流式截图时可能按会话分配 state，
 * 集中在一个 holder 也便于单元测试替换实现。
 */
class ControlSession(
    val appContext: Context,
    val capture: ScreenCaptureManager,
    val input: InputDispatcher,
) {
    val a11y: ControlAccessibilityService?
        get() = ControlAccessibilityService.current()

    /**
     * Routes 内活跃心跳回调，由 [HttpServer] 在 start 时注入。
     * 用于让 `/stream` 的每帧发送刷新 idle watchdog，避免活跃直播被判空闲。
     */
    @Volatile var activityTicker: (() -> Unit)? = null

    fun touchActivity() {
        activityTicker?.invoke()
    }
}
