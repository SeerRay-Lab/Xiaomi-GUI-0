# 架构说明

> 工程内部文档。只讲当前代码实际做的事，不讲规划、愿景、最佳实践。

## 做什么

Guiness 是一个**电脑控手机**的 GUI Agent——和 OpenClaw 一类思路相近：用户在桌面端下发自然语言指令，由 VLM 在真机 Android 上感知屏幕、决策、执行，闭环跑完整个任务。目标形态是日常手机操作的通用代理，当前代码只实现了基础链路：单轮 query → 循环「截图 → 推理 → 动作」直至 Complete / Fail / 超步。

Episode 的全过程数据（每步截图、模型思考、动作、原始回复）会按 `日期/app/episode_id/` 落盘。这份数据同时也就是评测数据——给人打分填 `eval_score` 就是评测，不填就是普通运行记录，两种模式共用同一套产物。

两种入口：
- `main.py`：PySide6 桌面端，产品主入口，一个对话 = 一次任务执行。
- `run_eval.py`：批跑 JSONL 的 CLI，用于回归/评测场景。

两条入口共享同一组件工厂（`core/setup.py`）和同一个执行引擎（`runner/episode_runner.py`）。差异只在组装：GUI 在 `QThread` 里调，CLI 在主线程里 for-loop。

## 分层

```
┌─────────────────────────────────────────────────────────────┐
│  entry           run_eval.py            main.py → gui/app    │
├─────────────────────────────────────────────────────────────┤
│  factory         core/setup.py   build_components / build_runner
├─────────────────────────────────────────────────────────────┤
│  engine          runner/episode_runner.py    EpisodeRunner   │
│                  reporter/                   进度回调协议    │
├─────────────────────────────────────────────────────────────┤
│  capabilities    device/   action/   model/   apps/          │
├─────────────────────────────────────────────────────────────┤
│  infra           core/config.py   gui/paths.py   utils/      │
└─────────────────────────────────────────────────────────────┘
```

下层不依赖上层。`core/` 是 config + 组件装配。`utils/` 现在只剩 `image_utils` 和 `config_loader` 的兼容壳。

## 关键合约

### Components（`core/setup.py`）

```python
@dataclass
class Components:
    adb: ADBController         # device/adb_controller.py
    automator: AutomatorDevice # device/automator.py (uiautomator2)
    inference: InferenceClient # model/inference_client.py
    executor: ActionExecutor   # action/action_executor.py
```

`build_components(device_id, device_type, model_config, on_progress)` 一把组装好。`on_progress` 是可选 `Callable[[str], None]`，GUI 把它转成 Qt signal 显示"正在连接 ADB..."，CLI 可以不传。

### Config

`core/config.py` 定义 `load_config_file(path)`、`get_config()`、`reload_config(path)`。结构：

```yaml
device:
  name: ""               # 空 → adb 自动选第一台
  device_type: phone     # phone | car | car-pin | car-full | pad
model:
  source: mify | custom
  model_name: ...
  mify_api_key: ...
  custom_url: ...
operation:
  max_steps, back_times, sleep_seconds_per_act,
  screen_sleep_time, max_history_images, max_turn,
  use_compress
compress:
  quality, pixel_factor, min_pixels, max_pixels
task:
  task_file: config/xxx.jsonl   # CLI/GUI 保存任务时都写这个
```

**约定**：内部库代码不再调 `get_*_config()` 读全局——上层拿 dict，`compress` 子 dict 显式传给 `compress_image()`，`model` 子 dict 显式传给 `InferenceClient`。`get_config()` 只保留给最外层入口。

### Reporter（`reporter/base.py`）

```python
class Reporter(Protocol):
    def on_episode_start(self, task: dict) -> None: ...
    def on_step_complete(self, step_record: dict) -> None: ...
    def on_episode_finish(self, result: dict) -> None: ...
```

引擎不打印任何东西，只回调 Reporter。
- CLI 用 `reporter/cli_reporter.py`，ANSI 染色 + 进度条。
- GUI 用 `NullReporter()`，真正的渲染走 `on_step_complete` → `QSignal` → `ChatFeed`。

## 执行流程

### 1. Episode 装配

```
config.yaml ─► load_config_file ─► dict
device_id ─── resolve_device_id（auto 或用户选）
model_cfg ─── config["model"]（GUI 可覆盖）
             │
             ▼
       build_components ─► adb, automator, inference, executor
                         │
                         ▼
      build_runner(components, config, output_dir, date_str,
                   stop_check, on_step_complete, reporter)
```

### 2. EpisodeRunner.run(task) 三段式

| 阶段 | 职责 |
| --- | --- |
| `_prepare_episode` | 填充元数据、建 `output_dir/<date>/<app>/<episode_id>/`、history 初始化 |
| `_run_step` × N | 截图 → XML dump → 压缩 → `inference.predict` → `normalize_action` → `executor.execute` → 追加 step_record → `reporter.on_step_complete` + `on_step_complete` 回调 |
| `_finalize_episode` | 深拷贝 episode 剥掉 `screenshot_time`（reporter 内部字段，不进磁盘）→ 写 `task.json` → 清 tmp → 按 `back_times` 按返回键 |

终止条件（任一即退出循环）：
- `stop_check()` 返回 True（GUI 停止按钮）
- `action.func ∈ {Complete, End, Speak, Fail}`
- `step >= max_steps`

### 3. 动作分发

`action/action_space.py` 的 `ACTION_REGISTRY` 定义合法 func + 必填字段。`action/action_executor.py` 按 func 路由到 adb / automator 的具体调用。Swipe 方向走表驱动 `_SWIPE_DIRECTIONS`。

### 4. 模型推理

`model/inference_client.py`：
- `source == "mify"` → mify 网关 + token auth，读 `model/prompts/mify.txt`。
- `source == "custom"` → 任意 OpenAI 兼容端点，读 `model/prompts/custom.txt`。

**重要**：`mify.txt` 和 `custom.txt` 是两份独立文件，即使内容当下高度相似也不合并参数化模板。两端后续会各自演进，合并会导致"一改改两份"。详见 [model/prompts/\_\_init\_\_.py](model/prompts/__init__.py) 的注释。

其他子模块：
- `preset_models.yaml`：mify 支持的模型清单（UI 下拉框数据源）。
- `response_parser.py`：解析 `<think>`/`<thought>` + `<answer>` JSON。
- `device_info.py`：device_type → 提示词里注入的"设备信息"字符串。

### 5. Apps 注册表

`apps/registry.py` 从 `apps/data/phone.yaml` / `car.yaml` 加载别名/包名映射，被 `action_executor` 的 `Open` 动作和 inference 的系统提示使用。加新 app 改 yaml 即可，不碰代码。

## GUI（`gui/`）

```
gui/
  app.py              QMainWindow 入口，持有 ChatManager + EpisodeWorker
  chat_manager.py     Conversation 数据类 + 线程安全存取 + 历史持久化
  paths.py            统一路径：project_root / resource_path / data_dir / config_file_path
  workers/
    episode_worker.py QThread：调 build_components / build_runner，把 runner 的回调转 Qt signal
  pages/
    config_page.py        评测配置页壳
    config/               ├─ model_section.py   ├─ task_section.py   ├─ advanced_section.py
    result_page.py        评测结果页壳
    result/               ├─ tree_section.py    └─ detail_section.py
  widgets/
    chat_feed, message_bubble, step_card, screenshot_viewer,
    input_bar, sidebar, settings_dialog, model_config_panel,
    log_viewer, collapsible_section
  styles/theme.qss
```

`pages/*/` 下的 section 模块是 **module-function** 风格——不是独立的 `QWidget` 子类，而是 `build_xxx(page)` + `on_yyy(page, ...)` 把控件挂到 `ConfigPage`/`ResultPage` 实例上。这么做是为了拆文件但不搬状态、不重接信号，降低视觉/行为回归风险。

### GUI 线程模型

- 主线程：UI + `ChatManager`（`threading.Lock` 保护 dict）。
- 每个运行中的 Episode 一个 `EpisodeWorker(QThread)`。
- Runner 的 `stop_check` 绑到 `conv.is_stop_requested`；停止按钮调 `ChatManager.stop` → `conv.request_stop()` → `threading.Event.set()`。
- Runner 的 `on_step_complete` 回调里直接 `self.step_completed.emit(conv.id, step_data)`，ChatFeed 监听该 signal 渲染。

**不要** 从外部读 `Conversation._stop_event` / `_stop_flag`——只用 `request_stop()` / `is_stop_requested()`。

## 数据产物

```
data/
  output/
    2026-04-20/
      weather/
        task_001/
          task.json          # episode 完整记录：query / app / phone / eval_score / data[]
          1.png              # 每步截图（压缩后）
          1.xml              # uiautomator 的 hierarchy dump
          2.png  2.xml  ...
  history/
    conversations.json       # GUI 的对话历史（无截图，仅元数据 + step 记录）
```

`task.json.data[i]` 字段：`step`、`foreground_app`、`thought`、`action`（原始）、`action_normalized`（加了绝对坐标）、`raw_model_output`、可能还有 `error`。**字段数量/命名在重构期间锁死**，改字段需同步检查 `gui/widgets/step_card.py` 和 `gui/pages/result/detail_section.py` 的显示逻辑。

## 打包

`build_config.spec` + `build.sh` 走 PyInstaller：
- `datas=` 包含 `config.yaml`、`apps/data/*.yaml`、`model/prompts/*.txt`、`model/preset_models.yaml`、`gui/styles/theme.qss`、`resources/`。
- `hiddenimports=` 覆盖 `apps.registry`、`core.config`、`core.setup`、`model.prompts`、`model.response_parser`、`model.device_info`、`reporter.*`。
- 运行时 `gui/paths.py::data_dir()` 判 `sys.frozen`：冻结时数据写 `~/Guiness/data/`，开发时写仓库内 `data/`。

## 修改提示（避免踩坑）

- **新增 action func**：改 `action/action_space.py::ACTION_REGISTRY` + `action/action_executor.py::_handlers` + `runner/episode_runner.py::_TERMINAL_FUNCS`（如果是终止动作）。三处 func 名必须完全一致，曾有 Tap/Click 命名分裂的 bug。
- **新增 device_type**：除了 `config.yaml` 下拉，还要看 `apps/data/` 是否需要新 yaml、`model/device_info.py` 的映射字典、`ADBController(task_type=...)` 的分支。
- **改 prompt**：直接改 `mify.txt` 或 `custom.txt`，不要试图抽公共部分。
- **改 task.json 结构**：同时改 `runner/episode_runner.py::_run_step` 写入、`gui/widgets/step_card.py` 读取、`gui/pages/result/detail_section.py::_display_step_info` 显示，否则历史数据会错位。
- **加 GUI 章节**：按 `pages/config/` 和 `pages/result/` 的 module-function 模式加，不要新建 `QWidget` 子类（除非是真正可复用的控件，那种放 `gui/widgets/`）。
