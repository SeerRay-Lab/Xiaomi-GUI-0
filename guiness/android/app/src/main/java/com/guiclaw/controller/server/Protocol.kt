package com.guiness.controller.server

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * HTTP 协议对象。Stage 2 只定义必要的字段，保持和 Python WifiBackend 一一对应。
 */

const val PROTOCOL_VERSION = "1"
const val AUTH_HEADER = "X-Guiness-Token"

@Serializable
data class Ok(
    val ok: Boolean = true,
    val version: String = PROTOCOL_VERSION,
    val serverTime: Long = System.currentTimeMillis(),
)

@Serializable
data class ErrorBody(
    val ok: Boolean = false,
    val code: String,
    val msg: String,
)

@Serializable
data class DeviceInfoResp(
    val ok: Boolean = true,
    val model: String,
    val osVersion: String,
    val sdk: Int,
    val width: Int,
    val height: Int,
    val density: Int,
    val name: String,
    val backendKind: String = "wifi",
    val protocolVersion: String = PROTOCOL_VERSION,
)

@Serializable
data class PermissionsStatus(
    val ok: Boolean = true,
    val accessibility: Boolean,
    val mediaProjection: Boolean,
)

@Serializable
data class TapReq(val x: Double, val y: Double)

@Serializable
data class LongPressReq(val x: Double, val y: Double, val durationMs: Int = 2000)

@Serializable
data class SwipeReq(
    val x1: Double,
    val y1: Double,
    val x2: Double,
    val y2: Double,
    val durationMs: Int = 400,
)

@Serializable
data class InputTextReq(
    val text: String,
    val clear: Boolean = false,
    val enter: Boolean = false,
    val position: List<Double>? = null,
)

@Serializable
data class InputTextResp(
    val ok: Boolean = true,
    val method: String, // "a11y_set_text" / "a11y_paste" / "noop"
)

@Serializable
data class KeyReq(val key: String)

@Serializable
data class ForegroundResp(
    val ok: Boolean = true,
    val appName: String,
    val pkg: String?,
    val activity: String? = null,
)

@Serializable
data class OpReq(val ok: Boolean = true, val method: String = "a11y")

@Serializable
data class OpenReq(
    @SerialName("package") val pkg: String,
)

@Serializable
data class OpenDeeplinkReq(val uri: String)

@Serializable
data class ForceStopReq(
    @SerialName("package") val pkg: String,
)

@Serializable
data class ForceStopAllReq(
    val packages: List<String> = emptyList(),
    val whitelist: List<String> = emptyList(),
)

@Serializable
data class ForceStopResp(
    val ok: Boolean = true,
    val degraded: Boolean = false,
    val stopped: List<String> = emptyList(),
)
