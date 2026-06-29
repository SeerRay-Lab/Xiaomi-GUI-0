package com.guiness.controller.util

import java.net.Inet4Address
import java.net.NetworkInterface

object NetworkUtils {

    /**
     * 枚举所有非 loopback 的 IPv4 接口地址，按优先级排序：
     * 1. wlan*（Wi-Fi）
     * 2. 其它 up 且非虚拟接口
     */
    fun listLocalIpv4(): List<Pair<String, String>> {
        val result = mutableListOf<Pair<String, String>>()
        try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return emptyList()
            for (nif in ifaces) {
                if (!nif.isUp || nif.isLoopback || nif.isVirtual) continue
                val name = nif.name ?: continue
                for (addr in nif.inetAddresses) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        result += name to (addr.hostAddress ?: continue)
                    }
                }
            }
        } catch (e: Exception) {
            AppLog.w("枚举网卡失败", e)
        }
        return result.sortedBy { (name, _) ->
            when {
                name.startsWith("wlan") -> 0
                name.startsWith("eth") -> 1
                else -> 2
            }
        }
    }

    fun preferredIpv4(): String? = listLocalIpv4().firstOrNull()?.second
}
