package com.guiness.controller.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ClearAll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.guiness.controller.ui.theme.LogError
import com.guiness.controller.ui.theme.LogInfo
import com.guiness.controller.ui.theme.LogWarn
import com.guiness.controller.util.AppLog
import kotlinx.coroutines.launch

private enum class LogFilter(val label: String) { ALL("全部"), INFO("信息"), WARN("警告"), ERROR("错误") }

/** Parse a line like "HH:mm:ss.SSS  I  message" → (level, timestamp, message). */
private data class ParsedLog(val level: Char, val timestamp: String, val message: String)

private fun parse(line: String): ParsedLog {
    // Expected format: "HH:mm:ss.SSS L  msg". Parsing is defensive — garbage stays as INFO.
    val parts = line.split(Regex("\\s+"), limit = 3)
    return if (parts.size >= 3 && parts[1].length == 1) {
        ParsedLog(level = parts[1][0], timestamp = parts[0], message = parts[2])
    } else {
        ParsedLog(level = 'I', timestamp = "", message = line)
    }
}

@Composable
fun LogScreen() {
    val lines = remember { mutableStateListOf<String>().apply { addAll(AppLog.snapshot()) } }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    var filter by remember { mutableStateOf(LogFilter.ALL) }

    LaunchedEffect(Unit) {
        AppLog.events.collect { line ->
            lines.add(line)
            if (lines.size > 400) repeat(lines.size - 400) { lines.removeAt(0) }
        }
    }

    val filtered by remember(filter) {
        derivedStateOf {
            val parsed = lines.map(::parse)
            when (filter) {
                LogFilter.ALL -> parsed
                LogFilter.INFO -> parsed.filter { it.level == 'I' }
                LogFilter.WARN -> parsed.filter { it.level == 'W' }
                LogFilter.ERROR -> parsed.filter { it.level == 'E' }
            }
        }
    }

    // Auto-scroll when new lines arrive, unless the user scrolled up manually
    val isAtBottom by remember {
        derivedStateOf {
            val last = listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1
            last >= filtered.size - 2
        }
    }
    LaunchedEffect(filtered.size) {
        if (isAtBottom && filtered.isNotEmpty()) {
            listState.animateScrollToItem(filtered.size - 1)
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        Column(Modifier.fillMaxSize()) {
            // Header row
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 4.dp),
            ) {
                Text(
                    "日志 · ${filtered.size}/${lines.size}",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onBackground,
                )
                OutlinedButton(
                    onClick = { lines.clear() },
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                ) {
                    Icon(Icons.Filled.ClearAll, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("清空", style = MaterialTheme.typography.labelMedium)
                }
            }

            // Filter chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                LogFilter.entries.forEach { f ->
                    FilterChip(
                        selected = filter == f,
                        onClick = { filter = f },
                        label = { Text(f.label, style = MaterialTheme.typography.labelMedium) },
                    )
                }
            }

            // Log list
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(MaterialTheme.shapes.medium)
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)),
            ) {
                if (filtered.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            "暂无日志",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                } else {
                    LazyColumn(
                        state = listState,
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(10.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        items(filtered) { entry -> LogRow(entry) }
                    }
                }
            }
        }

        // FAB: jump to latest when user has scrolled up
        AnimatedVisibility(
            visible = !isAtBottom && filtered.isNotEmpty(),
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp),
        ) {
            FloatingActionButton(
                onClick = {
                    scope.launch { listState.animateScrollToItem(filtered.size - 1) }
                },
                containerColor = MaterialTheme.colorScheme.primaryContainer,
                contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            ) {
                Icon(Icons.Filled.ArrowDownward, contentDescription = "跳到底部")
            }
        }
    }
}

@Composable
private fun LogRow(entry: ParsedLog) {
    val color = when (entry.level) {
        'W' -> LogWarn
        'E' -> LogError
        else -> LogInfo
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .background(color.copy(alpha = 0.06f))
            .padding(horizontal = 8.dp, vertical = 6.dp),
    ) {
        Box(
            Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(color),
        )
        Text(
            entry.timestamp,
            fontFamily = FontFamily.Monospace,
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            entry.level.toString(),
            fontFamily = FontFamily.Monospace,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            color = color,
        )
        Text(
            entry.message,
            fontFamily = FontFamily.Monospace,
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(1f),
        )
    }
}
