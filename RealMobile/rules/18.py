import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "打开抖音的自动连播"
TASK_ID = 18
STEPRULES = """评分规则（分阶段验证进度 - 2阶段简化版）

1. 打开抖音App → 总分:0.5

2. 打开/启用自动连播功能 → 总分:1.0

一票否决条件：
- 未打开抖音App → 分数:0
- 未找到/启用自动连播 → 分数:0

规则特点：
- 支持多XPath匹配，一个页面可匹配多条xpath
- 不使用break，使用布尔列表完整检查
- 完整的错误处理和异常捕捉
- 支持多路径input
"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """加载轨迹数据，优先使用 _ocr.xml，并正确计算实际点击坐标"""
    task_json_path = os.path.join(path, "task.json")
    with open(task_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    steps = data.get('data', data.get('steps', []))
    xml_strings = []
    actions = []

    for step in steps:
        # 优先使用 _ocr.xml
        xml_file = step['xml'].replace('.xml', '_ocr.xml')
        xml_path = os.path.join(path, xml_file)

        if not os.path.exists(xml_path):
            xml_path = os.path.join(path, step['xml'])

        if not os.path.exists(xml_path):
            continue

        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_strings.append(f.read())

        position_temp = step['pixel']
        if "plan" in step and "position" in step["plan"]:
            position_temp = [
                int(step['pixel'][0] * step['plan']['position'][0]),
                int(step['pixel'][1] * step['plan']['position'][1])
            ]

        action_dict = {
            "action": "click",
            "params": {"position": position_temp}
        }
        actions.append(action_dict)

    return xml_strings, actions


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音App"""
    rule1_xpaths = [
        "//*[contains(@package, 'douyin') or contains(@package, 'aweme')]",
        "//*[contains(@text, '抖音')]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
        for xpath_idx in range(len(rule1_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule1_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

        # 至少有一个xpath匹配即可通过规则1（打开抖音）
        if any(checked):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开抖音App"

    return False, "未打开抖音App"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开/启用自动连播功能"""
    rule2_xpaths = [
        # 自动连播相关页面或设置选项
        "//*[contains(@text, '设置') or contains(@text, '我') or contains(@text, '个人中心')]",
        # 查找自动连播/自动播放关键词
        "//*[(contains(@text, '自动连播') or contains(@text, '自动播放')) and bbox_contains_point(../@bounds, $point)]",
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
        for xpath_idx in range(len(rule2_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule2_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

        # 至少找到自动连播关键词（xpath_idx=1）即可算找到
        if checked[1]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开/启用自动连播功能"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未找到或启用自动连播"




def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 18,
            "path": "...",
            "steprules": "...",
            "total_score": 1.0,
            "details": [...]
        }
    """
    try:
        xml_strings, actions = load_trajectory_data(path)
    except Exception as e:
        print(f"Error loading trajectory data: {e}")
        return {
            "query": QUERY,
            "id": TASK_ID,
            "path": path,
            "steprules": STEPRULES,
            "total_score": 0.0,
            "details": [],
            "rejection_reason": "无法加载轨迹数据"
        }

    if not xml_strings:
        return {
            "query": QUERY,
            "id": TASK_ID,
            "path": path,
            "steprules": STEPRULES,
            "total_score": 0.0,
            "details": [],
            "rejection_reason": "轨迹数据为空"
        }

    # 评估两个规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)

    # 一票否决：规则1未满足则规则2不计分
    if not rule1_satisfied:
        rule2_satisfied = False

    # 计算最终分数
    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.5
    if rule2_satisfied:
        max_score = 1.0

    # 构建详细信息
    details = [
        {
            "rule": "1. 打开抖音App",
            "score": 0.5,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 打开/启用自动连播功能",
            "score": 1.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        }
    ]

    return {
        "query": QUERY,
        "id": TASK_ID,
        "path": path,
        "steprules": STEPRULES,
        "total_score": max_score,
        "details": details,
        "rejection_reason": None
    }


if __name__ == "__main__":
    # 支持多路径测试
    # test_paths = [
    #     "BMK/first/deb304a8",
    #     "BMK/2026-04-29/抖音/BMK评测/f767a3be-e24c-414a-9455-1e47cc27b668",
    #     "BMK/second/6c5f1341",
    #     "BMK/third/48b01659",
    #     "BMK/fourth/5fb8079f"
    # ]
    test_paths = [
        "BMK/first/deb304a8",
        "BMK/2026-04-29/抖音/BMK评测/f767a3be-e24c-414a-9455-1e47cc27b668",
        "BMK/sample/a6ccce10",
        "BMK/sample/d34af8e5"
    ]
    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 如果没有找到任何路径，使用第一个作为示例
            print(f"\n评估路径: {test_paths[0]}")
            result = evaluate_trajectory(path=test_paths[0])
            print(json.dumps(result, ensure_ascii=False, indent=2))
