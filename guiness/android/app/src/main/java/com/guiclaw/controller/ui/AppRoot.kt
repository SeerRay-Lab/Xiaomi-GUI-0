package com.guiness.controller.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cable
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Terminal
import androidx.compose.material.icons.outlined.Cable
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Terminal
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.guiness.controller.GuinessApp
import com.guiness.controller.R
import com.guiness.controller.ui.components.StatusChip
import com.guiness.controller.ui.components.StatusTone

private data class NavItem(
    val label: String,
    val iconSelected: ImageVector,
    val iconUnselected: ImageVector,
)

private val NAV_ITEMS = listOf(
    NavItem("状态", Icons.Filled.Dashboard, Icons.Outlined.Dashboard),
    NavItem("连接", Icons.Filled.Cable, Icons.Outlined.Cable),
    NavItem("日志", Icons.Filled.Terminal, Icons.Outlined.Terminal),
    NavItem("关于", Icons.Filled.Info, Icons.Outlined.Info),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppRoot(
    state: GuinessApp.ServerState,
    token: String,
    ip: String?,
    accessibilityOn: Boolean,
    bgLaunchOn: Boolean,
    onToggle: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
    onOpenBgLaunchSettings: () -> Unit,
    onRefresh: () -> Unit,
    onRegenerateToken: () -> Unit,
    onCopy: (label: String, value: String) -> Unit = { _, _ -> },
    onStartScan: () -> Unit = {},
) {
    var tab by remember { mutableIntStateOf(0) }

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Row(
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(10.dp),
                    ) {
                        Image(
                            painter = painterResource(id = R.drawable.guiness_logo),
                            contentDescription = null,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier
                                .size(28.dp)
                                .clip(CircleShape),
                        )
                        Text(
                            "Guiness 控制器",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                },
                actions = {
                    StatusChip(
                        label = if (state.running) "运行中" else "已停止",
                        tone = if (state.running) StatusTone.OK else StatusTone.Neutral,
                        modifier = Modifier.padding(end = 12.dp),
                    )
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
                windowInsets = WindowInsets.statusBars,
            )
        },
        bottomBar = {
            NavigationBar(
                containerColor = MaterialTheme.colorScheme.surface,
                tonalElevation = 3.dp,
            ) {
                NAV_ITEMS.forEachIndexed { index, item ->
                    val selected = tab == index
                    NavigationBarItem(
                        selected = selected,
                        onClick = { tab = index },
                        icon = {
                            Icon(
                                imageVector = if (selected) item.iconSelected else item.iconUnselected,
                                contentDescription = item.label,
                            )
                        },
                        label = {
                            Text(
                                item.label,
                                style = MaterialTheme.typography.labelMedium,
                            )
                        },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.onSecondaryContainer,
                            selectedTextColor = MaterialTheme.colorScheme.onSurface,
                            indicatorColor = MaterialTheme.colorScheme.secondaryContainer,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                    )
                }
            }
        },
        containerColor = MaterialTheme.colorScheme.background,
        contentWindowInsets = WindowInsets.safeDrawing,
    ) { pad ->
        AnimatedContent(
            targetState = tab,
            modifier = Modifier
                .fillMaxSize()
                .padding(pad),
            transitionSpec = {
                val forward = targetState > initialState
                (slideInHorizontally(animationSpec = tween(220)) { w -> if (forward) w / 6 else -w / 6 } +
                    fadeIn(tween(220))) togetherWith
                    (slideOutHorizontally(animationSpec = tween(180)) { w -> if (forward) -w / 6 else w / 6 } +
                        fadeOut(tween(180)))
            },
            label = "tab-transition",
        ) { targetTab ->
            when (targetTab) {
                0 -> StatusScreen(
                    state = state,
                    accessibilityOn = accessibilityOn,
                    bgLaunchOn = bgLaunchOn,
                    ip = ip,
                    onToggle = onToggle,
                    onOpenAccessibilitySettings = onOpenAccessibilitySettings,
                    onOpenBgLaunchSettings = onOpenBgLaunchSettings,
                    onRefresh = onRefresh,
                )
                1 -> ConnectionScreen(
                    state = state,
                    token = token,
                    ip = ip,
                    onRegenerateToken = onRegenerateToken,
                    onCopy = onCopy,
                    onStartScan = onStartScan,
                )
                2 -> LogScreen()
                else -> AboutScreen(
                    accessibilityOn = accessibilityOn,
                    projectionOn = state.running,
                    bgLaunchOn = bgLaunchOn,
                    onOpenAccessibilitySettings = onOpenAccessibilitySettings,
                    onOpenBgLaunchSettings = onOpenBgLaunchSettings,
                )
            }
        }
    }
}
