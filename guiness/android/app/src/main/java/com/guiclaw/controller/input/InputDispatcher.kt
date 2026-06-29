package com.guiness.controller.input

import android.graphics.Path
import com.guiness.controller.service.ControlAccessibilityService
import com.guiness.controller.util.AppLog
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * 把 tap / long_press / swipe 映射到 AccessibilityService.dispatchGesture。
 *
 * 所有注入通过 ReentrantLock 串行：dispatchGesture 对同一 Service 并发不稳。
 */
class InputDispatcher {
    private val lock = ReentrantLock()

    private fun a11y(): ControlAccessibilityService? {
        val s = ControlAccessibilityService.current()
        if (s == null) AppLog.w("a11y 未就绪")
        return s
    }

    fun tap(x: Float, y: Float): Boolean = lock.withLock {
        val s = a11y() ?: return false
        val path = Path().apply { moveTo(x, y) }
        s.dispatchGestureSync(path, startDelayMs = 0, durationMs = 50)
    }

    fun longPress(x: Float, y: Float, durationMs: Long = 2000): Boolean = lock.withLock {
        val s = a11y() ?: return false
        val path = Path().apply { moveTo(x, y) }
        s.dispatchGestureSync(path, startDelayMs = 0, durationMs = durationMs.coerceAtLeast(200))
    }

    fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long = 400): Boolean = lock.withLock {
        val s = a11y() ?: return false
        val path = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        s.dispatchGestureSync(path, startDelayMs = 0, durationMs = durationMs.coerceAtLeast(50))
    }
}
