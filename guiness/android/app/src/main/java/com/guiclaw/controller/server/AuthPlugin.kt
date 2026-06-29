package com.guiness.controller.server

import com.guiness.controller.util.AppLog
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.Application
import io.ktor.server.application.ApplicationCallPipeline
import io.ktor.server.application.call
import io.ktor.server.request.path
import io.ktor.server.response.respond

/**
 * 所有请求都要带 X-Guiness-Token 并与当前 token 一致，否则 401。
 *
 * expectedToken 每次请求惰性获取——token 在用户"重置"后立即生效，无需重启 server。
 * 不给任何 endpoint 开白：/ping 也带 token，防止暴露到外网扫描器后被探测。
 *
 * onAuthorized：鉴权通过后触发，用于更新"最后活跃时间戳"。
 */
fun Application.installGuinessAuth(
    expectedToken: () -> String,
    onAuthorized: () -> Unit = {},
) {
    intercept(ApplicationCallPipeline.Plugins) {
        val actual = call.request.headers[AUTH_HEADER].orEmpty()
        val expected = expectedToken()
        if (expected.isBlank() || actual != expected) {
            AppLog.w("401 ${call.request.path()} token=${if (actual.isBlank()) "(missing)" else "mismatch"}")
            call.respond(
                HttpStatusCode.Unauthorized,
                ErrorBody(code = "unauthorized", msg = "invalid token"),
            )
            finish()
            return@intercept
        }
        onAuthorized()
    }
}
