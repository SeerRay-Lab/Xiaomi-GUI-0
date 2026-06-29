# GUI Agent Benchmark (guiagentbmk)

一个用于**评测移动端 GUI 智能体（GUI Agent）**的基准测试与评分框架。

智能体（如 `GuiClaw`，底层基于 Claude 等大模型）在真实安卓手机上操作中文 App（哔哩哔哩、QQ、抖音、小红书、微博、淘宝、QQ音乐、携程、高德地图等）完成自然语言任务。本仓库记录智能体执行过程中的「轨迹」（截图 + UI 层级 XML + OCR + 动作），并用**人工编写的规则脚本**对每条轨迹打分，最终汇总成功率。

## 目录结构

```
guiagentbmk/
├── rules/                       # 评分脚本（核心）
│   ├── evaluator_xpath.py       # 评测引擎：XML 解析 + XPath 匹配
│   ├── 1.py ... 143.py          # 每个文件 = 一个评测任务的评分规则
│   └── __pycache__/
├── BMK/                         # 轨迹数据（多批测试运行）
│   ├── first/  second/  third/  fourth/   # 各批次的轨迹文件夹
│   └── 2026-04-29/              # 按 App 组织的人工标注数据（b站、qq、抖音…）
├── paddle/                      # PaddleOCR 模型（生成 _ocr.xml 时使用）
│   ├── det/ rec/ cls/ doc_ori/  # 检测 / 识别 / 方向分类 / 文档朝向模型
├── results/                     # 评测输出（JSON / CSV / XLSX）
├── query_comparison_report.json # 任务查询 ↔ 模型轨迹的对照报告
└── README.md
```

## 核心概念

### 轨迹（Trajectory）
每个轨迹是一个文件夹（如 `BMK/first/67037d53/`），代表智能体执行一次任务的完整过程：

| 文件 | 含义 |
|------|------|
| `task.json` | 任务元信息 + 每一步动作（query、app、手机型号、点击坐标、thought 等） |
| `N.xml` | 第 N 步的安卓 UI 层级树（`uiautomator dump`） |
| `N_ocr.xml` | 经 PaddleOCR 增强、带 `ocr_texts` 属性的 XML（评分时优先使用） |
| `N.png` / `N.jpg` | 第 N 步的屏幕截图 |
| `N.json` | 第 N 步的动作元数据 |
| `N_error.txt` | 该步的错误日志（若有） |

### 评分规则（rules/N.py）
每个 `rules/N.py` 对应一个评测任务，自带：
- `QUERY` —— 任务指令，如 `"关闭b站后台播放"`
- `TASK_ID` —— 任务编号
- `STEPRULES` —— 人类可读的分步评分标准
- `evaluate_rule_X()` —— 单步评分函数，用 XPath 匹配 UI 元素 + 点击坐标
- `evaluate_trajectory(path)` —— 入口函数，返回该轨迹的得分字典

评分采用**分步累加**：多步任务按 0.33 / 0.66 / 1.0 渐进给分，`total_score` 范围 0.0~1.0。

### 评测引擎（evaluator_xpath.py）
- 把安卓 UI XML 解析成元素列表，支持 `text`、`ocr_texts`、`bounds`、`checked` 等属性
- 提供类 XPath 匹配，并扩展了自定义函数 `bbox_contains_point(@bounds, $point)`——判断智能体的点击坐标是否落在目标元素的包围盒内
- 核心函数 `evaluate_action_xml(xml, xpath, action_dict)` 返回是否匹配

## 使用方法

### 环境依赖
```bash
pip install lxml
# OCR 预处理步骤还需 PaddleOCR（模型已放在 paddle/ 目录）
```
其余均为 Python 标准库（`json`、`os`、`re` 等）。

### 评测单个任务
每个规则脚本的 `__main__` 里硬编码了若干批次的轨迹路径，直接运行即可：
```bash
cd /mnt/vlm-ks3/wuqinzhuo/guiagentbmk
python rules/1.py
```
输出该任务在各轨迹上的得分 JSON。

### 在代码中调用
```python
import sys
sys.path.append("rules")
import importlib
mod = importlib.import_module("1")          # 加载 rules/1.py

result = mod.evaluate_trajectory("BMK/first/67037d53")
# {
#   "query": "关闭b站后台播放",
#   "id": 1,
#   "total_score": 1.0,
#   "details": [{"rule": ..., "score": 0.33, "satisfied": true, "evidence": "第9步..."}, ...]
# }
```

### 查看汇总结果
`results/` 目录下的 `evaluation_results_<时间戳>.json` 是批量评测的汇总，结构为：
```json
{
  "summary": {
    "total_tasks": 108,
    "total_paths": 433,
    "total_success": 393,
    "total_success_rate": 0.9076,
    "overall_avg_score": 0.9295
  },
  "results": [
    {
      "id": 1,
      "query": "关闭b站后台播放",
      "scores_list": [1.0, 1.0, ...],
      "success_rate": 1.0,
      "path_results": [ { "path": "...", "score": 1.0, "details": [...] } ]
    }
  ]
}
```
同一份数据另有 `.csv` / `.xlsx` 版本，方便用表格查看。

## 工作流程概览

```
智能体在手机上跑任务
        ↓
采集轨迹（截图 + uiautomator XML + 动作坐标）  →  BMK/<批次>/<episode_id>/
        ↓
PaddleOCR 增强 XML（生成 _ocr.xml）             ←  paddle/
        ↓
rules/N.py 用 XPath 规则逐步打分（evaluator_xpath.py）
        ↓
汇总得分与成功率                                →  results/
```

## 备注
- 数据中可见的手机型号示例：Redmi 12 5G / 小米 14 Pro Ti，安卓 13/15。
- `task` 字段标注为 `GuiClaw`，部分为「GuiClaw人工标注」黄金轨迹。
- `query_comparison_report.json` 记录了 108 条查询与对应模型（如 `claude-opus-4-7`）轨迹的映射，用于跨模型/版本对比。
- 目前共 **108 个评测任务、433 条轨迹**，整体成功率约 **90.8%**。
