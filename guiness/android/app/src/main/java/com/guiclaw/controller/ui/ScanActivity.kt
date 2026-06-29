package com.guiness.controller.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.guiness.controller.GuinessApp
import com.guiness.controller.pairing.PairingClient
import com.guiness.controller.pairing.PairingPayload
import com.guiness.controller.ui.theme.GuinessTheme
import com.guiness.controller.util.AppLog
import com.guiness.controller.util.NetworkUtils
import com.guiness.controller.util.TokenStore
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/**
 * 扫二维码配对。
 *
 * 状态机（见 ScanState）：
 *  - CheckingPermission → Previewing → Detected(payload) → Pairing → Success/Failed
 *  - PermissionDenied 独立一条；Failed 可以通过"重新扫码"回到 Previewing
 *
 * 成功后 finish()，MainActivity 的 launcher 拿到 RESULT_OK。
 */
class ScanActivity : ComponentActivity() {

    private val state = MutableStateFlow<ScanState>(ScanState.CheckingPermission)

    private val cameraPermissionRequest = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        state.value = if (granted) ScanState.Previewing else ScanState.PermissionDenied
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            GuinessTheme {
                val s by state.collectAsState()
                ScanScreen(
                    state = s,
                    onRequestPermission = { cameraPermissionRequest.launch(Manifest.permission.CAMERA) },
                    onBarcodeDetected = { handleBarcode(it) },
                    onRetry = { state.value = ScanState.Previewing },
                    onCancel = { finish() },
                )
            }
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED) {
            state.value = ScanState.Previewing
        } else {
            cameraPermissionRequest.launch(Manifest.permission.CAMERA)
        }
    }

    /** 扫到码时调来。在相机分析线程；UI 切换交给 state flow。 */
    private fun handleBarcode(text: String) {
        val payload = PairingPayload.parse(text)
        if (payload == null) {
            AppLog.w("扫到无效二维码：$text")
            return  // 无效码就不断扫，等到有效的为止
        }
        if (payload.v != com.guiness.controller.pairing.PAYLOAD_VERSION) {
            state.value = ScanState.Failed("协议版本不匹配：${payload.v}")
            return
        }
        if (payload.isExpired()) {
            state.value = ScanState.Failed("二维码已过期，请在 PC 上重新生成")
            return
        }
        // 去抖：同一 payload 进入 Detected 后不再处理后续帧
        if (state.value is ScanState.Detected ||
            state.value is ScanState.Pairing ||
            state.value is ScanState.Success) return

        state.value = ScanState.Detected(payload)
        // 自动进入 pairing，不需要用户再点一次
        doPair(payload)
    }

    private fun doPair(payload: PairingPayload) {
        state.value = ScanState.Pairing(payload)
        val app = application as GuinessApp
        val phoneIp = NetworkUtils.preferredIpv4()
        val phonePort = app.state.value.port
        val phoneToken = TokenStore.get(this).current()
        val phoneName = Build.MODEL ?: Build.DEVICE ?: "Android"

        if (phoneIp == null) {
            state.value = ScanState.Failed("未获取到本机局域网 IP")
            return
        }
        if (phonePort <= 0) {
            state.value = ScanState.Failed("控制服务未运行，请先在主页点击启动")
            return
        }

        lifecycleScope.launch {
            val result = PairingClient.pair(
                payload = payload,
                phoneIp = phoneIp,
                phonePort = phonePort,
                phoneToken = phoneToken,
                phoneName = phoneName,
            )
            state.value = when (result) {
                is PairingClient.Result.Ok -> ScanState.Success(payload)
                is PairingClient.Result.Failed -> ScanState.Failed(result.reason)
            }
            if (result is PairingClient.Result.Ok) {
                // 给用户 700ms 看到成功再关
                kotlinx.coroutines.delay(700)
                finish()
            }
        }
    }

}

// ── State ────────────────────────────────────────────────────────

sealed class ScanState {
    data object CheckingPermission : ScanState()
    data object PermissionDenied : ScanState()
    data object Previewing : ScanState()
    data class Detected(val payload: PairingPayload) : ScanState()
    data class Pairing(val payload: PairingPayload) : ScanState()
    data class Success(val payload: PairingPayload) : ScanState()
    data class Failed(val reason: String) : ScanState()
}

// ── UI ───────────────────────────────────────────────────────────

@Composable
private fun ScanScreen(
    state: ScanState,
    onRequestPermission: () -> Unit,
    onBarcodeDetected: (String) -> Unit,
    onRetry: () -> Unit,
    onCancel: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black),
    ) {
        when (state) {
            is ScanState.CheckingPermission -> CenteredMessage("正在检查权限…")
            is ScanState.PermissionDenied -> PermissionDeniedBlock(onRequestPermission, onCancel)
            is ScanState.Previewing -> CameraPreview(onBarcodeDetected = onBarcodeDetected, onCancel = onCancel)
            is ScanState.Detected -> CenteredMessage("识别成功，正在配对…")
            is ScanState.Pairing -> PairingBlock(state.payload)
            is ScanState.Success -> SuccessBlock(state.payload)
            is ScanState.Failed -> FailedBlock(state.reason, onRetry, onCancel)
        }
    }
}

@Composable
private fun CenteredMessage(text: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text, color = Color.White, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun PermissionDeniedBlock(onRequest: () -> Unit, onCancel: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("需要相机权限才能扫码", color = Color.White, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(16.dp))
        Button(onClick = onRequest) { Text("授予相机权限") }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = onCancel) { Text("取消") }
    }
}

@Composable
private fun PairingBlock(payload: PairingPayload) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator(color = Color.White)
        Spacer(Modifier.height(20.dp))
        Text("正在配对 ${payload.pcName}", color = Color.White, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text("${payload.pcIp}:${payload.pcPort}", color = Color.White.copy(alpha = 0.7f))
    }
}

@Composable
private fun SuccessBlock(payload: PairingPayload) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.CheckCircle, null, tint = Color(0xFF4CAF50), modifier = Modifier.size(72.dp))
        Spacer(Modifier.height(16.dp))
        Text("已配对 ${payload.pcName}", color = Color.White, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun FailedBlock(reason: String, onRetry: () -> Unit, onCancel: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.Error, null, tint = Color(0xFFEF5350), modifier = Modifier.size(72.dp))
        Spacer(Modifier.height(16.dp))
        Text("配对失败", color = Color.White, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Text(reason, color = Color.White.copy(alpha = 0.8f))
        Spacer(Modifier.height(24.dp))
        Button(onClick = onRetry, modifier = Modifier.fillMaxWidth()) { Text("重新扫码") }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) { Text("返回") }
    }
}

@OptIn(ExperimentalGetImage::class)
@Composable
private fun CameraPreview(onBarcodeDetected: (String) -> Unit, onCancel: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val previewView = remember { PreviewView(context) }
    val executor = remember { Executors.newSingleThreadExecutor() }
    val scanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build()
        )
    }

    LaunchedEffect(Unit) {
        val providerFuture = ProcessCameraProvider.getInstance(context)
        val provider = withContext(Dispatchers.IO) { providerFuture.get() }

        val preview = Preview.Builder().build().also {
            it.setSurfaceProvider(previewView.surfaceProvider)
        }
        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .apply {
                setAnalyzer(executor) { imageProxy ->
                    processImage(imageProxy, scanner, onBarcodeDetected)
                }
            }

        try {
            provider.unbindAll()
            provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                analysis,
            )
        } catch (e: Exception) {
            AppLog.e("绑定相机失败", e)
        }
    }

    Box(Modifier.fillMaxSize()) {
        AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())

        // 顶部说明 + 底部取消按钮
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color.Black.copy(alpha = 0.55f))
                .padding(16.dp),
        ) {
            Text(
                "将相机对准电脑屏幕上的二维码",
                color = Color.White,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.align(Alignment.Center),
            )
        }

        OutlinedButton(
            onClick = onCancel,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 32.dp),
        ) { Text("取消", color = Color.White) }
    }
}

@SuppressLint("UnsafeOptInUsageError")
@OptIn(ExperimentalGetImage::class)
private fun processImage(
    imageProxy: androidx.camera.core.ImageProxy,
    scanner: com.google.mlkit.vision.barcode.BarcodeScanner,
    onBarcode: (String) -> Unit,
) {
    val media = imageProxy.image
    if (media == null) {
        imageProxy.close()
        return
    }
    val input = InputImage.fromMediaImage(media, imageProxy.imageInfo.rotationDegrees)
    scanner.process(input)
        .addOnSuccessListener { barcodes ->
            barcodes.firstOrNull()?.rawValue?.let(onBarcode)
        }
        .addOnFailureListener { AppLog.w("barcode scan 失败", it) }
        .addOnCompleteListener { imageProxy.close() }
}
