package com.guiness.controller.util

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Process
import android.provider.Settings

/**
 * 后台启 Activity 的授权探测 + 引导入口。
 *
 * 为什么单独拉一个 util：`/open` 在 Xiaomi HyperOS / MIUI 上经常失败，原因是厂商在 AOSP
 * BAL 之上额外加了一个 MIUIOP 10021（安全中心里显示为「后台弹出界面」）。它不对 a11y
 * service 给豁免，`requestPermissions()` 也请求不到，只能引导用户去设置页手开。
 *
 * isGranted 两路判断都走：
 *   1) `Settings.canDrawOverlays` — AOSP 侧 SYSTEM_ALERT_WINDOW，部分 MIUI 版本依赖这个
 *   2) 反射 `AppOpsManager.checkOpNoThrow(10021, ...)` — MIUI 自家的那条
 * 任一放行即认为可以从后台启 Activity。
 */
object BackgroundLaunchPermission {

    /** MIUI「后台弹出界面」对应的 appop code。AOSP 上 ≤10000，这个区间是厂商自留的。 */
    private const val MIUI_OP_BACKGROUND_START_ACTIVITY = 10021

    fun isGranted(ctx: Context): Boolean {
        if (Settings.canDrawOverlays(ctx)) return true
        return miuiBackgroundStartAllowed(ctx)
    }

    private fun miuiBackgroundStartAllowed(ctx: Context): Boolean {
        return try {
            val aom = ctx.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
            val m = AppOpsManager::class.java.getMethod(
                "checkOpNoThrow",
                Int::class.javaPrimitiveType,
                Int::class.javaPrimitiveType,
                String::class.java,
            )
            val mode = m.invoke(aom, MIUI_OP_BACKGROUND_START_ACTIVITY, Process.myUid(), ctx.packageName) as Int
            mode == AppOpsManager.MODE_ALLOWED
        } catch (_: Throwable) {
            false
        }
    }

    fun openSettings(ctx: Context) {
        val tries = listOf(
            Intent("miui.intent.action.APP_PERM_EDITOR").apply {
                setClassName(
                    "com.miui.securitycenter",
                    "com.miui.permcenter.permissions.PermissionsEditorActivity",
                )
                putExtra("extra_pkgname", ctx.packageName)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            },
            Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:${ctx.packageName}"),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            Intent(
                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:${ctx.packageName}"),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
        for (i in tries) {
            try {
                ctx.startActivity(i)
                return
            } catch (_: Throwable) {
            }
        }
        AppLog.w("所有后台弹出权限跳转入口都失败")
    }
}
