package com.guiness.controller.ui

import androidx.compose.foundation.Image
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
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.FormatListNumbered
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.guiness.controller.R
import com.guiness.controller.ui.components.SectionCard
import com.guiness.controller.ui.components.StatusChip
import com.guiness.controller.ui.components.StatusTone

@Composable
fun AboutScreen(
    accessibilityOn: Boolean,
    projectionOn: Boolean,
    bgLaunchOn: Boolean,
    onOpenAccessibilitySettings: () -> Unit,
    onOpenBgLaunchSettings: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        // Hero / app identity
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier
                .fillMaxWidth()
                .clip(MaterialTheme.shapes.large)
                .background(MaterialTheme.colorScheme.primaryContainer)
                .padding(18.dp),
        ) {
            Image(
                painter = painterResource(id = R.drawable.guiness_logo),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .size(64.dp)
                    .clip(CircleShape),
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    "Guiness 控制器",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
                Text(
                    "v0.1.0 · Wi-Fi 模式",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f),
                )
            }
        }

        // Permission setup flow (ordered steps)
        SectionCard(
            title = "配置权限流程",
            icon = Icons.Filled.FormatListNumbered,
            subtitle = "按顺序完成授权即可接入 PC",
        ) {
            FlowStep(
                index = 1,
                title = "开启无障碍服务",
                description = "在系统设置中开启 Guiness 的无障碍开关，用于注入点击 / 滑动。",
                mode = FlowMode.Manual,
                granted = accessibilityOn,
                actionLabel = if (!accessibilityOn) "前往设置" else null,
                onAction = if (!accessibilityOn) onOpenAccessibilitySettings else null,
            )
            FlowConnector()
            FlowStep(
                index = 2,
                title = "允许后台弹出",
                description = "MIUI / ColorOS / OneUI 等厂商还需额外打开「后台弹界面」。",
                mode = FlowMode.Manual,
                granted = bgLaunchOn,
                actionLabel = if (!bgLaunchOn) "前往设置" else null,
                onAction = if (!bgLaunchOn) onOpenBgLaunchSettings else null,
            )
            FlowConnector()
            FlowStep(
                index = 3,
                title = "授权录屏",
                description = "无需提前配置。首次在「状态」页点击「启动服务」时系统会自动弹窗。",
                mode = FlowMode.Automatic,
                granted = projectionOn,
                actionLabel = null,
                onAction = null,
            )
        }

        // Detailed permission panel
        SectionCard(
            title = "权限总览",
            icon = Icons.Filled.LockOpen,
            subtitle = "三项均授权后 PC 才能正常接入",
        ) {
            PermissionDetail(
                icon = Icons.Filled.Accessibility,
                title = "无障碍服务",
                body = "用于注入点击、滑动、文本输入等手势。系统被重置后需要重新开启。",
                granted = accessibilityOn,
                actionLabel = if (!accessibilityOn) "前往设置" else null,
                onAction = if (!accessibilityOn) onOpenAccessibilitySettings else null,
            )
            Spacer(Modifier.height(12.dp))
            PermissionDetail(
                icon = Icons.Filled.Videocam,
                title = "录屏 (MediaProjection)",
                body = "持续截图给 PC 端 VLM。在「状态」页点击启动服务时会弹出系统授权。",
                granted = projectionOn,
                actionLabel = null,
                onAction = null,
            )
            Spacer(Modifier.height(12.dp))
            PermissionDetail(
                icon = Icons.Filled.FlashOn,
                title = "后台弹出界面",
                body = "MIUI / ColorOS / OneUI 等需要额外开启后台弹出 & 电池优化白名单。",
                granted = bgLaunchOn,
                actionLabel = if (!bgLaunchOn) "前往设置" else null,
                onAction = if (!bgLaunchOn) onOpenBgLaunchSettings else null,
            )
        }

        // Tips
        SectionCard(
            title = "使用小贴士",
            icon = Icons.Filled.Lightbulb,
            subtitle = "首次接入常见问题",
        ) {
            TipLine("PC 端与手机必须处于同一 Wi-Fi，公共 Wi-Fi 禁用。")
            TipLine("若 PC 出现 401，检查 Token 是否正确；可在「连接」页重置。")
            TipLine("若提示 503 / accessibility_disabled，重新开启无障碍即可。")
            TipLine("MIUI 请允许「锁屏显示 + 后台弹界面」两个开关。")
        }

        // Disclaimer
        SectionCard(
            title = "安全声明",
            icon = Icons.Filled.Info,
            subtitle = "明文 HTTP · 仅局域网",
        ) {
            Text(
                "本应用不使用 TLS，请仅在可信局域网下启用控制服务。Token 在本地 EncryptedSharedPreferences 中加密存储，不会上传。",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }

        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun PermissionDetail(
    icon: ImageVector,
    title: String,
    body: String,
    granted: Boolean,
    actionLabel: String?,
    onAction: (() -> Unit)?,
) {
    Row(
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
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                StatusChip(
                    label = if (granted) "已授权" else "未授权",
                    tone = if (granted) StatusTone.OK else StatusTone.Warning,
                )
            }
            Text(
                body,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
            if (actionLabel != null && onAction != null) {
                Spacer(Modifier.height(6.dp))
                OutlinedButton(
                    onClick = onAction,
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                ) {
                    Text(actionLabel, style = MaterialTheme.typography.labelMedium)
                    Spacer(Modifier.width(4.dp))
                    Icon(Icons.AutoMirrored.Filled.OpenInNew, contentDescription = null, modifier = Modifier.size(14.dp))
                }
            }
        }
    }
}

private enum class FlowMode { Manual, Automatic }

@Composable
private fun FlowStep(
    index: Int,
    title: String,
    description: String,
    mode: FlowMode,
    granted: Boolean,
    actionLabel: String?,
    onAction: (() -> Unit)?,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(
                    if (granted) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.primaryContainer
                ),
            contentAlignment = Alignment.Center,
        ) {
            if (granted) {
                Icon(
                    imageVector = Icons.Filled.Check,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.size(18.dp),
                )
            } else {
                Text(
                    index.toString(),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
        }
        Column(modifier = Modifier.weight(1f)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                FlowModeBadge(mode = mode)
            }
            Text(
                description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
            if (actionLabel != null && onAction != null) {
                Spacer(Modifier.height(6.dp))
                OutlinedButton(
                    onClick = onAction,
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                ) {
                    Text(actionLabel, style = MaterialTheme.typography.labelMedium)
                    Spacer(Modifier.width(4.dp))
                    Icon(Icons.AutoMirrored.Filled.OpenInNew, contentDescription = null, modifier = Modifier.size(14.dp))
                }
            }
        }
    }
}

@Composable
private fun FlowModeBadge(mode: FlowMode) {
    val (label, icon, container, onContainer) = when (mode) {
        FlowMode.Manual -> Quadruple(
            "手动",
            Icons.Filled.FlashOn,
            MaterialTheme.colorScheme.tertiaryContainer,
            MaterialTheme.colorScheme.onTertiaryContainer,
        )
        FlowMode.Automatic -> Quadruple(
            "自动",
            Icons.Filled.AutoAwesome,
            MaterialTheme.colorScheme.secondaryContainer,
            MaterialTheme.colorScheme.onSecondaryContainer,
        )
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier
            .clip(MaterialTheme.shapes.small)
            .background(container)
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = onContainer,
            modifier = Modifier.size(12.dp),
        )
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Medium,
            color = onContainer,
        )
    }
}

private data class Quadruple<A, B, C, D>(val a: A, val b: B, val c: C, val d: D)

@Composable
private fun FlowConnector() {
    Row(modifier = Modifier.fillMaxWidth()) {
        Box(
            modifier = Modifier
                .width(32.dp)
                .padding(vertical = 4.dp),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier
                    .width(2.dp)
                    .height(14.dp)
                    .background(MaterialTheme.colorScheme.outlineVariant),
            )
        }
    }
}

@Composable
private fun TipLine(text: String) {
    Row(
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.padding(vertical = 3.dp),
    ) {
        Box(
            Modifier
                .size(6.dp)
                .padding(top = 7.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primary),
        )
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(1f),
        )
    }
}
