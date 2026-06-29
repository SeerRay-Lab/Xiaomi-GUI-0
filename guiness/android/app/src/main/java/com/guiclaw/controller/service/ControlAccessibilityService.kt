package com.guiness.controller.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Bundle
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.guiness.controller.util.AppLog
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.max

/**
 * Guiness 唯一的手势/按键/文本注入通道。
 *
 * 不使用任何 ROOT / ADB 能力：
 *  - 手势：AccessibilityService.dispatchGesture（API 24+）
 *  - 文本：AccessibilityNodeInfo.ACTION_SET_TEXT（直接替换焦点 EditText）
 *  - 导航：performGlobalAction(BACK/HOME/RECENTS)
 *  - KeyEvent（ENTER/DELETE 等）：通过 focused 节点的 ACTION_SET_TEXT 或下发到 IME
 *
 * 靠 current() 暴露单例引用：HttpServer 启动时从这里取；若用户未开启则返回 null。
 */
class ControlAccessibilityService : AccessibilityService() {

    @Volatile private var latestPackage: String? = null
    @Volatile private var latestActivity: String? = null

    /**
     * 自动吞 MIUI/HyperOS「启动应用」弹窗的临时窗口。
     * `/open` 调用 startActivity 之前会把这个时间戳推到未来 N ms，弹窗出现时直接找
     * 「始终允许」/「本次允许」按钮点掉；时间窗过后不再介入，避免误点。
     */
    @Volatile private var autoApproveUntilMs: Long = 0L

    override fun onServiceConnected() {
        INSTANCE = this
        AppLog.i("无障碍服务已连接")
    }

    override fun onDestroy() {
        if (INSTANCE === this) INSTANCE = null
        AppLog.w("无障碍服务已断开")
        super.onDestroy()
    }

    override fun onInterrupt() {
        AppLog.w("无障碍服务被中断")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            event.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
        ) {
            val pkg = event.packageName?.toString()
            val cls = event.className?.toString()
            if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
                if (!pkg.isNullOrBlank()) latestPackage = pkg
                if (!cls.isNullOrBlank()) latestActivity = cls
            }
            if (System.currentTimeMillis() < autoApproveUntilMs &&
                pkg != null && pkg in LAUNCH_DIALOG_PACKAGES
            ) {
                tryClickLaunchAllowButton()
            }
        }
    }

    // ============ 自动点击「启动应用」弹窗 ============

    /**
     * 给 `/open` 用：在调 startActivity 之前 arm 一个短时窗。弹窗出现时自动点掉
     * 「始终允许」（优先）或「本次允许」。
     */
    fun armAutoApproveLaunchDialog(durationMs: Long = 4000L) {
        autoApproveUntilMs = System.currentTimeMillis() + durationMs
    }

    private fun tryClickLaunchAllowButton() {
        val root = rootInActiveWindow ?: return
        for (label in LAUNCH_ALLOW_LABELS) {
            val nodes = root.findAccessibilityNodeInfosByText(label) ?: continue
            for (node in nodes) {
                if (node == null) continue
                // 精确匹配文本，避免误触到含「允许」的其他控件
                val text = node.text?.toString()?.trim()
                if (text != label) continue
                if (performClickSelfOrAncestor(node)) {
                    AppLog.i("auto-approve: 点击了「$label」")
                    autoApproveUntilMs = 0L   // 一次足够
                    return
                }
            }
        }
    }

    private fun performClickSelfOrAncestor(node: AccessibilityNodeInfo): Boolean {
        var n: AccessibilityNodeInfo? = node
        var depth = 0
        while (n != null && depth < 5) {
            if (n.isClickable) {
                return n.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            }
            n = n.parent
            depth++
        }
        return false
    }

    // ============ 手势分发（同步语义，给 InputDispatcher 用） ============

    fun dispatchGestureSync(path: Path, startDelayMs: Long, durationMs: Long, timeoutMs: Long = 3000): Boolean {
        val stroke = GestureDescription.StrokeDescription(path, startDelayMs, max(1, durationMs))
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val latch = CountDownLatch(1)
        var ok = false
        val dispatched = dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(g: GestureDescription?) { ok = true; latch.countDown() }
            override fun onCancelled(g: GestureDescription?) { ok = false; latch.countDown() }
        }, null)
        if (!dispatched) {
            AppLog.w("dispatchGesture 返回 false")
            return false
        }
        if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) {
            AppLog.w("dispatchGesture 超时 ${timeoutMs}ms")
            return false
        }
        return ok
    }

    // ============ 文本输入 ============

    /**
     * 向当前 focused EditText 写入文本。
     * clear=true 用 ACTION_SET_TEXT 直接替换（原生 API，不依赖键盘）。
     * 返回值：设置成功时的方法名（a11y_set_text / a11y_paste / noop）。
     */
    fun setText(text: String, clear: Boolean): String {
        val target = findFocusedEditable() ?: run {
            AppLog.w("未找到焦点可编辑节点")
            return "noop"
        }
        val bundle = Bundle()
        val finalText = if (clear) text else {
            val existing = target.text?.toString() ?: ""
            existing + text
        }
        bundle.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, finalText)
        val ok = target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, bundle)
        return if (ok) "a11y_set_text" else "noop"
    }

    private fun findFocusedEditable(): AccessibilityNodeInfo? {
        // 1. 输入焦点
        findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.let { if (it.isEditable) return it }
        // 2. 可达性焦点
        findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)?.let { if (it.isEditable) return it }
        // 3. root 向下 BFS 找第一个 editable（fallback）
        val root = rootInActiveWindow ?: return null
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue += root
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            if (n.isEditable) return n
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue += it }
            }
        }
        return null
    }

    // ============ 按键 / 导航 ============

    fun back(): Boolean = performGlobalAction(GLOBAL_ACTION_BACK)
    fun home(): Boolean = performGlobalAction(GLOBAL_ACTION_HOME)
    fun recents(): Boolean = performGlobalAction(GLOBAL_ACTION_RECENTS)

    /**
     * 支持：BACK / HOME / RECENTS / ENTER / DELETE / KEYCODE_* / 纯数字 keycode
     */
    fun pressKeyByName(key: String): Boolean {
        val normalized = key.trim().uppercase().removePrefix("KEYCODE_")
        return when (normalized) {
            "BACK" -> back()
            "HOME" -> home()
            "RECENTS", "RECENT_APPS" -> recents()
            "ENTER" -> dispatchKeyToFocused(KeyEvent.KEYCODE_ENTER)
            "DELETE", "DEL" -> dispatchKeyToFocused(KeyEvent.KEYCODE_DEL)
            else -> {
                val code = normalized.toIntOrNull() ?: run {
                    AppLog.w("未知按键: $key")
                    return false
                }
                dispatchKeyToFocused(code)
            }
        }
    }

    private fun dispatchKeyToFocused(keyCode: Int): Boolean {
        // AccessibilityService 上 API 不能直接发 KeyEvent（除非 canFilterKeyEvents + 拦截时注入）。
        // 但对 EditText 的 ENTER 可以：IME 场景下 performAction + SET_TEXT 加入换行；更稳妥的是
        // 对 focused 节点试 performAction(IME_ENTER)。此处简化实现：追加 \n 触发下一步。
        if (keyCode == KeyEvent.KEYCODE_ENTER) {
            val target = findFocusedEditable() ?: return false
            val existing = target.text?.toString() ?: ""
            val bundle = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "$existing\n")
            }
            return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, bundle)
        }
        if (keyCode == KeyEvent.KEYCODE_DEL) {
            val target = findFocusedEditable() ?: return false
            val existing = target.text?.toString() ?: ""
            if (existing.isEmpty()) return true
            val bundle = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, existing.dropLast(1))
            }
            return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, bundle)
        }
        AppLog.w("不支持的 keyCode: $keyCode（A11y 无法直接下发 KeyEvent）")
        return false
    }

    // ============ 前台应用 ============

    fun foregroundPackageAndActivity(): Pair<String?, String?> {
        val pkg = latestPackage ?: rootInActiveWindow?.packageName?.toString()
        val act = latestActivity
        return pkg to act
    }

    companion object {
        @Volatile private var INSTANCE: ControlAccessibilityService? = null

        /** Server 端用这个拿到当前连接的服务实例；未启用时 null。 */
        fun current(): ControlAccessibilityService? = INSTANCE

        /**
         * 承载「启动应用」弹窗的已知包名。Xiaomi HyperOS/MIUI 上实际出弹窗的组件在这里
         * 几家轮换（不同 ROM 版本不一样）。有新发现往里面塞就行。
         */
        private val LAUNCH_DIALOG_PACKAGES = setOf(
            "com.miui.securitycenter",
            "com.miui.thirdappassistant",
            "com.lbe.security.miui",
            "android",
        )

        /** 按钮文案候选，顺序即优先级：总是允许 > 允许一次 > 仅裸文本「允许」兜底。 */
        private val LAUNCH_ALLOW_LABELS = listOf(
            "始终允许",
            "总是允许",
            "允许",
            "本次允许",
            "允许一次",
        )
    }
}
