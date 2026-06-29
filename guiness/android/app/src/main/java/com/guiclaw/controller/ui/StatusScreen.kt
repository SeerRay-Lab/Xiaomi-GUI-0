package com.guiness.controller.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.Accessibility
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.Lan
import androidx.compose.material.icons.filled.PauseCircle
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.WifiTethering
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.guiness.controller.GuinessApp
import com.guiness.controller.ui.components.InfoTile
import com.guiness.controller.ui.components.SectionCard
import com.guiness.controller.ui.components.StatusChip
import com.guiness.controller.ui.components.StatusTone

@Composable
fun StatusScreen(
    state: GuinessApp.ServerState,
    accessibilityOn: Boolean,
    bgLaunchOn: Boolean,
    ip: String?,
    onToggle: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
    onOpenBgLaunchSettings: () -> Unit,
    onRefresh: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        HeroStatusCard(state = state, ip = ip, onToggle = onToggle)

        // Quick stats grid
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            InfoTile(
                label = "端口",
                value = if (state.running && state.port > 0) state.port.toString() else "--",
                icon = Icons.Filled.Lan,
                modifier = Modifier.weight(1f),
            )
            InfoTile(
                label = "局域网 IP",
                value = ip ?: "--",
                icon = Icons.Filled.WifiTethering,
                modifier = Modifier.weight(1f),
            )
        }

        // Permissions
        SectionCard(
            title = "权限状态",
            icon = Icons.Filled.Shield,
        ) {
            PermissionRow(
                icon = Icons.Filled.Accessibility,
                label = "无障碍服务",
                granted = accessibilityOn,
                actionLabel = "去开启",
                onAction = onOpenAccessibilitySettings,
            )
            Spacer(Modifier.height(10.dp))
            PermissionRow(
                icon = Icons.Filled.Videocam,
                label = "录屏授权",
                granted = state.running,
                actionLabel = null,
                onAction = null,
            )
            Spacer(Modifier.height(10.dp))
            PermissionRow(
                icon = Icons.Filled.FlashOn,
                label = "后台弹出",
                granted = bgLaunchOn,
                actionLabel = if (bgLaunchOn) null else "去开启",
                onAction = if (bgLaunchOn) null else onOpenBgLaunchSettings,
            )
        }

        // Refresh row
        OutlinedButton(
            onClick = onRefresh,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Filled.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text("刷新状态")
        }

        Text(
            "提示：PC 需与本机处于同一 Wi-Fi。明文 HTTP 仅限可信局域网使用。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 4.dp),
        )
    }
}

@Composable
private fun HeroStatusCard(
    state: GuinessApp.ServerState,
    ip: String?,
    onToggle: () -> Unit,
) {
    val running = state.running
    val gradient = if (running) {
        Brush.linearGradient(
            listOf(
                MaterialTheme.colorScheme.primary,
                MaterialTheme.colorScheme.secondary,
            ),
        )
    } else {
        Brush.linearGradient(
            listOf(
                MaterialTheme.colorScheme.surfaceVariant,
                MaterialTheme.colorScheme.surface,
            ),
        )
    }
    val onGradient = if (running) {
        MaterialTheme.colorScheme.onPrimary
    } else {
        MaterialTheme.colorScheme.onSurface
    }
    val endpoint = when {
        !running -> "未启动"
        ip == null -> "http://?:${state.port}"
        else -> "http://$ip:${state.port}"
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(MaterialTheme.shapes.extraLarge)
                .background(gradient)
                .padding(20.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = "控制端点",
                        style = MaterialTheme.typography.labelLarge,
                        color = onGradient.copy(alpha = 0.85f),
                    )
                    PulseIndicator(active = running)
                }

                Text(
                    text = endpoint,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = FontFamily.Monospace,
                    color = onGradient,
                )

                Text(
                    text = if (running) "PC 输入上方地址与 Token 即可接入" else "点击下方按钮启动服务",
                    style = MaterialTheme.typography.bodyMedium,
                    color = onGradient.copy(alpha = 0.8f),
                )

                Button(
                    onClick = onToggle,
                    modifier = Modifier.fillMaxWidth(),
                    colors = if (running) {
                        ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer,
                            contentColor = MaterialTheme.colorScheme.onErrorContainer,
                        )
                    } else {
                        ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.tertiaryContainer,
                            contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
                        )
                    },
                ) {
                    Icon(
                        imageVector = if (running) Icons.Filled.PauseCircle else Icons.Filled.PlayCircle,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(if (running) "停止服务" else "启动服务")
                }
            }
        }
    }
}

@Composable
private fun PulseIndicator(active: Boolean) {
    val dotColor by animateColorAsState(
        targetValue = if (active) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.outline,
        animationSpec = tween(300),
        label = "dot-color",
    )
    val alpha by animateFloatAsState(
        targetValue = if (active) 1f else 0.5f,
        animationSpec = tween(300),
        label = "dot-alpha",
    )
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(dotColor.copy(alpha = alpha)),
        )
        Text(
            if (active) "LIVE" else "IDLE",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onPrimary.copy(alpha = if (active) 0.9f else 0.7f),
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun PermissionRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    granted: Boolean,
    actionLabel: String?,
    onAction: (() -> Unit)?,
    description: String? = null,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(18.dp),
            )
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
            if (description != null) {
                Text(
                    description,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        if (!granted && actionLabel != null && onAction != null) {
            OutlinedButton(
                onClick = onAction,
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
            ) {
                Text(actionLabel, style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.width(4.dp))
                Icon(Icons.AutoMirrored.Filled.OpenInNew, contentDescription = null, modifier = Modifier.size(14.dp))
            }
        } else {
            StatusChip(
                label = if (granted) "已授权" else "未授权",
                tone = if (granted) StatusTone.OK else StatusTone.Warning,
            )
        }
    }
}
