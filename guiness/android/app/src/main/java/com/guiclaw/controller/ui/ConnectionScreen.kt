package com.guiness.controller.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.guiness.controller.GuinessApp
import com.guiness.controller.ui.components.SectionCard

@Composable
fun ConnectionScreen(
    state: GuinessApp.ServerState,
    token: String,
    ip: String?,
    onRegenerateToken: () -> Unit,
    onCopy: (label: String, value: String) -> Unit,
    onStartScan: () -> Unit = {},
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        // 扫码配对入口：醒目大按钮放最顶
        SectionCard(
            title = "扫码配对 PC",
            icon = Icons.Filled.QrCodeScanner,
            subtitle = "PC 端点击「扫码配对」显示二维码后，点此扫码自动连接",
        ) {
            Button(
                onClick = onStartScan,
                modifier = Modifier.fillMaxWidth(),
                enabled = state.running,
            ) {
                Icon(Icons.Filled.QrCodeScanner, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(if (state.running) "开始扫码" else "请先启动服务")
            }
        }
        // Endpoint
        SectionCard(
            title = "连接端点",
            icon = Icons.Filled.Dns,
            subtitle = "PC 端 config.yaml → wifi_endpoint",
        ) {
            val endpoint = when {
                !state.running -> "未启动"
                ip == null -> "http://?:${state.port}"
                else -> "http://$ip:${state.port}"
            }
            ValueBlock(value = endpoint, monospace = true)
            Spacer(Modifier.height(10.dp))
            FilledTonalButton(
                onClick = { if (state.running && ip != null) onCopy("端点", endpoint) },
                enabled = state.running && ip != null,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Filled.ContentCopy, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp))
                Text("复制端点")
            }
        }

        // Token
        SectionCard(
            title = "访问 Token",
            icon = Icons.Filled.Key,
        ) {
            val pretty = if (token.length == 6) "${token.substring(0, 3)} ${token.substring(3)}" else token
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(MaterialTheme.shapes.medium)
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(vertical = 18.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    pretty,
                    fontSize = 40.sp,
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = FontFamily.Monospace,
                    letterSpacing = 6.sp,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(
                    onClick = { onCopy("Token", token) },
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Filled.ContentCopy, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("复制")
                }
                OutlinedButton(
                    onClick = onRegenerateToken,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Filled.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("重置")
                }
            }
        }
    }
}

@Composable
private fun ValueBlock(value: String, monospace: Boolean = false) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.medium)
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 14.dp, vertical = 14.dp),
    ) {
        Text(
            value,
            style = MaterialTheme.typography.titleMedium,
            fontFamily = if (monospace) FontFamily.Monospace else FontFamily.Default,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}
