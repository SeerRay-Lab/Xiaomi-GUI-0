# -*- coding: utf-8 -*-
"""ConfigPage 的「高级设置」章节：设备选择 + 操作参数，整体折叠。

设备区支持 USB / WiFi 两种模式（Stage 3）：
- USB：设备下拉 + 刷新按钮（沿用原 ADB 流程）
- WiFi：endpoint + token + 测试连接（走 WifiBackend）
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit,
)

from gui.widgets.collapsible_section import CollapsibleSection
from gui.styles import tokens as t


def build_advanced_section(page) -> QWidget:
    section = CollapsibleSection("高级设置（设备、操作参数）")
    content_lay = section.content_layout()

    # ── 模式切换行 ──
    mode_row = QHBoxLayout()
    mode_row.setSpacing(12)
    lbl_mode = QLabel("连接方式")
    lbl_mode.setFixedWidth(80)
    mode_row.addWidget(lbl_mode)

    page._mode_combo = QComboBox()
    page._mode_combo.addItem("USB (ADB)", "usb")
    page._mode_combo.addItem("WiFi", "wifi")
    page._mode_combo.setFixedWidth(180)
    page._fields["device.mode"] = page._mode_combo
    mode_row.addWidget(page._mode_combo)

    lbl_dtype = QLabel("类型")
    lbl_dtype.setFixedWidth(36)
    mode_row.addWidget(lbl_dtype)

    page._fields["device.device_type"] = QComboBox()
    page._fields["device.device_type"].addItems(["phone", "car", "car-pin", "car-full", "pad"])
    page._fields["device.device_type"].setFixedWidth(110)
    mode_row.addWidget(page._fields["device.device_type"])

    mode_row.addStretch(1)
    content_lay.addLayout(mode_row)

    # ── USB 行：设备序列号下拉 + 刷新 ──
    page._usb_row_widget = QWidget()
    usb_row = QHBoxLayout(page._usb_row_widget)
    usb_row.setContentsMargins(0, 0, 0, 0)
    usb_row.setSpacing(12)

    lbl_dev = QLabel("设备")
    lbl_dev.setFixedWidth(80)
    usb_row.addWidget(lbl_dev)

    page._device_combo = QComboBox()
    page._device_combo.setEditable(True)
    page._device_combo.setPlaceholderText("留空自动检测，或选择/输入设备序列号")
    page._fields["device.name"] = page._device_combo
    usb_row.addWidget(page._device_combo, 1)

    btn_refresh = QPushButton("刷新设备")
    btn_refresh.setObjectName("ghostButton")
    btn_refresh.setFixedWidth(80)
    btn_refresh.clicked.connect(lambda: refresh_devices(page))
    usb_row.addWidget(btn_refresh)

    content_lay.addWidget(page._usb_row_widget)

    # ── WiFi 行：endpoint + token + 测试连接 ──
    page._wifi_row_widget = QWidget()
    wifi_row = QHBoxLayout(page._wifi_row_widget)
    wifi_row.setContentsMargins(0, 0, 0, 0)
    wifi_row.setSpacing(12)

    lbl_ep = QLabel("IP 地址")
    lbl_ep.setFixedWidth(80)
    wifi_row.addWidget(lbl_ep)

    page._wifi_endpoint_edit = QLineEdit()
    page._wifi_endpoint_edit.setPlaceholderText("192.168.x.y")
    page._fields["device.wifi_endpoint"] = page._wifi_endpoint_edit
    wifi_row.addWidget(page._wifi_endpoint_edit, 2)

    lbl_tk = QLabel("Token")
    lbl_tk.setFixedWidth(50)
    wifi_row.addWidget(lbl_tk)

    page._wifi_token_edit = QLineEdit()
    page._wifi_token_edit.setPlaceholderText("APP 屏幕上显示的 token")
    page._fields["device.token"] = page._wifi_token_edit
    wifi_row.addWidget(page._wifi_token_edit, 2)

    btn_scan = QPushButton("扫码配对")
    btn_scan.setObjectName("ghostButton")
    btn_scan.setFixedWidth(90)
    btn_scan.setToolTip("电脑显示二维码，手机 Guiness 控制器扫码即可配对")
    btn_scan.clicked.connect(lambda: open_pairing_dialog(page))
    wifi_row.addWidget(btn_scan)

    btn_test = QPushButton("测试连接")
    btn_test.setObjectName("ghostButton")
    btn_test.setFixedWidth(90)
    btn_test.clicked.connect(lambda: test_wifi_connection(page))
    wifi_row.addWidget(btn_test)

    content_lay.addWidget(page._wifi_row_widget)

    page._mode_combo.currentIndexChanged.connect(lambda _i: _apply_mode_visibility(page))
    _apply_mode_visibility(page)

    # ── Parameters grid ──
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(10)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(3, 1)

    r = 0
    grid.addWidget(QLabel("最大步数"), r, 0)
    page._fields["operation.max_steps"] = QSpinBox()
    page._fields["operation.max_steps"].setRange(1, 100)
    grid.addWidget(page._fields["operation.max_steps"], r, 1)

    back_row = QHBoxLayout()
    back_row.setContentsMargins(0, 0, 0, 0)
    back_row.setSpacing(8)

    page._return_home_check = QCheckBox("任务结束后返回桌面")
    page._return_home_check.setToolTip("未勾选时任务完成后保持在当前页面；勾选后按右侧次数执行返回")
    back_row.addWidget(page._return_home_check)

    page._fields["operation.back_times"] = QSpinBox()
    page._fields["operation.back_times"].setRange(0, 20)
    page._fields["operation.back_times"].setFixedWidth(60)
    page._fields["operation.back_times"].setEnabled(False)
    back_row.addWidget(page._fields["operation.back_times"])
    back_row.addStretch(1)

    grid.addLayout(back_row, r, 2, 1, 2)

    def _on_return_home_toggled(checked: bool) -> None:
        spin = page._fields["operation.back_times"]
        spin.setEnabled(checked)
        if checked:
            if spin.value() == 0:
                spin.setValue(page._back_times_last or 6)
        else:
            if spin.value() > 0:
                page._back_times_last = spin.value()
            spin.setValue(0)

    page._back_times_last = 6
    page._return_home_check.toggled.connect(_on_return_home_toggled)
    page._fields["operation.back_times"].valueChanged.connect(
        lambda v: _sync_return_home_from_value(page, v)
    )

    r += 1
    grid.addWidget(QLabel("操作间隔(秒)"), r, 0)
    page._fields["operation.sleep_seconds_per_act"] = QDoubleSpinBox()
    page._fields["operation.sleep_seconds_per_act"].setRange(0, 30)
    page._fields["operation.sleep_seconds_per_act"].setSingleStep(0.5)
    grid.addWidget(page._fields["operation.sleep_seconds_per_act"], r, 1)

    grid.addWidget(QLabel("截图等待(秒)"), r, 2)
    page._fields["operation.screen_sleep_time"] = QDoubleSpinBox()
    page._fields["operation.screen_sleep_time"].setRange(0, 10)
    page._fields["operation.screen_sleep_time"].setSingleStep(0.1)
    grid.addWidget(page._fields["operation.screen_sleep_time"], r, 3)

    r += 1
    grid.addWidget(QLabel("历史图片数"), r, 0)
    page._fields["operation.max_history_images"] = QSpinBox()
    page._fields["operation.max_history_images"].setRange(0, 20)
    grid.addWidget(page._fields["operation.max_history_images"], r, 1)

    grid.addWidget(QLabel("历史轮数"), r, 2)
    page._fields["operation.max_turn"] = QSpinBox()
    page._fields["operation.max_turn"].setRange(0, 20)
    grid.addWidget(page._fields["operation.max_turn"], r, 3)

    r += 1
    page._fields["operation.use_compress"] = QCheckBox("启用图片压缩")
    grid.addWidget(page._fields["operation.use_compress"], r, 0, 1, 2)

    content_lay.addLayout(grid)

    page._collapsible_advanced = section
    section.expand()  # 默认展开，避免首次上手看不到连接方式切换
    return section


def _sync_return_home_from_value(page, value: int) -> None:
    """当 SpinBox 被外部（load）改写时，保持 checkbox 与其一致。"""
    check = getattr(page, "_return_home_check", None)
    if check is None:
        return
    target = value > 0
    if check.isChecked() != target:
        check.blockSignals(True)
        check.setChecked(target)
        check.blockSignals(False)
    page._fields["operation.back_times"].setEnabled(target)
    if value > 0:
        page._back_times_last = value


def sync_return_home_state(page) -> None:
    """config_page 在 load 完后调用，根据当前 back_times 值回显 checkbox。"""
    spin = page._fields.get("operation.back_times")
    if spin is None:
        return
    _sync_return_home_from_value(page, spin.value())


def current_mode(page) -> str:
    """读 mode combo 的 userData（'usb' / 'wifi'），兼容旧文本值。"""
    data = page._mode_combo.currentData()
    if isinstance(data, str) and data in ("usb", "wifi"):
        return data
    text = (page._mode_combo.currentText() or "").lower()
    return "wifi" if "wifi" in text else "usb"


def _apply_mode_visibility(page) -> None:
    mode = current_mode(page)
    page._usb_row_widget.setVisible(mode == "usb")
    page._wifi_row_widget.setVisible(mode == "wifi")


def refresh_devices(page) -> None:
    """USB 模式下刷新设备下拉；WiFi 模式下安静跳过。"""
    if current_mode(page) != "usb":
        return
    try:
        from device.adb_controller import list_all_devices
        devices = list_all_devices()
        current = page._device_combo.currentText()
        page._device_combo.clear()
        page._device_combo.addItems(devices)
        if current and current in devices:
            page._device_combo.setCurrentText(current)
        elif current:
            page._device_combo.setEditText(current)
        page._save_status.setText(f"检测到 {len(devices)} 个设备")
    except Exception as e:
        page._save_status.setText(f"设备检测失败: {e}")


def open_pairing_dialog(page) -> None:
    """打开扫码配对弹窗；成功后回填 endpoint/token 并自动触发测试连接。"""
    from gui.widgets.pairing_dialog import PairingDialog

    # 切到 WiFi 模式，避免用户在 USB 模式误点后没反应
    if current_mode(page) != "wifi":
        page._mode_combo.setCurrentIndex(page._mode_combo.findData("wifi"))

    dlg = PairingDialog(parent=page)

    def on_paired(result):
        # result.endpoint() 形如 "192.168.1.88:8765"，直接塞进 endpoint 输入框
        page._wifi_endpoint_edit.setText(result.endpoint())
        page._wifi_token_edit.setText(result.phone_token)
        page._save_status.setText(
            f"已通过扫码配对：{result.phone_name or result.phone_ip}"
        )
        page._save_status.setStyleSheet(
            f"color: {t.SUCCESS}; font-size: {t.FONT_XS}px; background: transparent;"
        )

    dlg.paired.connect(on_paired)
    dlg.exec()
    # 若用户扫过：走一次测试连接，给出"连接成功：xx xx"回执
    if dlg.result_payload() is not None:
        test_wifi_connection(page)


def test_wifi_connection(page) -> None:
    """构造一个临时 WifiBackend 探活：/ping + /device_info。"""
    endpoint = page._wifi_endpoint_edit.text().strip()
    token = page._wifi_token_edit.text().strip()
    err_style = f"color: {t.DANGER}; font-size: {t.FONT_XS}px; background: transparent;"
    ok_style = f"color: {t.SUCCESS}; font-size: {t.FONT_XS}px; background: transparent;"
    if not endpoint:
        page._save_status.setText("测试失败：端点为空")
        page._save_status.setStyleSheet(err_style)
        return
    try:
        from device.wifi_backend import WifiBackend
        be = WifiBackend(endpoint=endpoint, token=token, timeout=2.5)
        be.connect()
        info = be.device_info()
        be.close()
        page._save_status.setText(
            f"连接成功：{info.model} {info.width}x{info.height}"
        )
        page._save_status.setStyleSheet(ok_style)
    except PermissionError as e:
        page._save_status.setText(f"连接失败（Token）: {e}")
        page._save_status.setStyleSheet(err_style)
    except Exception as e:
        page._save_status.setText(f"连接失败: {e}")
        page._save_status.setStyleSheet(err_style)
