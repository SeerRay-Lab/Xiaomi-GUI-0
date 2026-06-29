package com.guiness.controller.util

import android.util.Log
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 轻量日志：logcat + 内存环形缓冲 + Flow（给 LogScreen 订阅）。
 *
 * 不持久化落盘：日常 20 行以内、崩溃看 logcat 就够了；省得踩文件 I/O + 权限。
 */
object AppLog {
    private const val TAG = "Guiness"
    private const val MAX_BUFFER = 200

    private val buffer = ArrayDeque<String>()
    private val _events = MutableSharedFlow<String>(extraBufferCapacity = 64)
    val events: SharedFlow<String> = _events.asSharedFlow()

    private val fmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)

    @Synchronized
    fun snapshot(): List<String> = buffer.toList()

    @JvmStatic
    fun i(msg: String) {
        Log.i(TAG, msg)
        record("I", msg)
    }

    @JvmStatic
    fun w(msg: String, t: Throwable? = null) {
        if (t != null) Log.w(TAG, msg, t) else Log.w(TAG, msg)
        record("W", msg + (t?.let { "  ${it.javaClass.simpleName}: ${it.message}" } ?: ""))
    }

    @JvmStatic
    fun e(msg: String, t: Throwable? = null) {
        if (t != null) Log.e(TAG, msg, t) else Log.e(TAG, msg)
        record("E", msg + (t?.let { "  ${it.javaClass.simpleName}: ${it.message}" } ?: ""))
    }

    private fun record(level: String, msg: String) {
        val line = "${fmt.format(Date())} $level  $msg"
        synchronized(buffer) {
            buffer.addLast(line)
            while (buffer.size > MAX_BUFFER) buffer.removeFirst()
        }
        _events.tryEmit(line)
    }
}
