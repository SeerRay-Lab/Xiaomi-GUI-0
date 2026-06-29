import json
import os
import sys
from typing import Dict, List, Any, Tuple

# 导入已有的工具函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "打开qq夜间模式"
TASK_ID = 4
STEPRULES = """1. 进入QQ APP → 总分:0.25

2.1 在外观/深色模式中开启"夜间模式/始终深色" → 总分:1.0
2.2 在个人中心页中点击夜间按钮或发现页面上出现日间按钮 → 总分:1.0"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """加载轨迹数据，优先使用 _ocr.xml"""
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
            # 如果 _ocr.xml 不存在，使用原始文件
            xml_path = os.path.join(path, step['xml'])

        if not os.path.exists(xml_path):
            continue

        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_strings.append(f.read())

        # 构造 action_dict 格式
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
    """规则1：进入QQ APP"""
    rule1_xpaths = [
        "//*[contains(@package, 'qq') or contains(@package, 'QQ') or contains(@text, 'QQ') or contains(@ocr_texts, 'QQ')]",
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule1_xpaths) - 1, -1, -1):
            xpath = rule1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 进入QQ APP"

    return False, "未进入QQ APP"


def evaluate_rule_2_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2.1：在外观/深色模式中开启"夜间模式/始终深色"，并确认界面变暗"""
    rule2_1_xpaths = [
        "//*[contains(@text, '深色模式') or contains(@ocr_texts, '深色模式') or contains(@text, '夜间模式') or contains(@ocr_texts, '夜间模式')]",
        "//*[contains(@text, '始终深色') or contains(@ocr_texts, '始终深色') ]"
    ]

    checked = [False] * len(rule2_1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule2_1_xpaths)):
            xpath = rule2_1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在设置中开启了夜间模式"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_1_xpaths)}"

    return False, "未进入设置或未开启夜间模式"


def evaluate_rule_2_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2.2：在个人中心页中点击夜间按钮或发现页面上出现日间按钮"""
    rule2_2_xpaths = [
        "//*[contains(@text, '夜间') or contains(@ocr_texts, '夜间') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '日间') or contains(@ocr_texts, '日间')]",
    ]

    checked = [False] * len(rule2_2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule2_2_xpaths)):
            xpath = rule2_2_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 页面中出现夜间/日间按钮或夜间模式已启用"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_2_xpaths)}"

    return False, "未检测到夜间模式启用"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "打开qq夜间模式",
            "id": 4,
            "path": "BMK/...",
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

    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_1_satisfied, rule2_1_evidence = evaluate_rule_2_1(xml_strings, actions)
    rule2_2_satisfied, rule2_2_evidence = evaluate_rule_2_2(xml_strings, actions)

    # 规则2是2.1和2.2的互补关系，只需满足一个
    rule2_satisfied = rule2_1_satisfied or rule2_2_satisfied
    rule2_evidence = rule2_1_evidence if rule2_1_satisfied else rule2_2_evidence

    details = [
        {
            "rule": "进入QQ APP",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2.1 在外观/深色模式中开启\"夜间模式/始终深色\"",
            "score": 0.75 if rule2_1_satisfied else 0.0,
            "satisfied": rule2_1_satisfied,
            "evidence": rule2_1_evidence
        },
        {
            "rule": "2.2 在个人中心页中点击夜间按钮或发现页面上出现日间按钮",
            "score": 0.75 if rule2_2_satisfied else 0.0,
            "satisfied": rule2_2_satisfied,
            "evidence": rule2_2_evidence
        }
    ]

    # 最终总分 = rule1 + max(rule2_1, rule2_2)
    rule1_score = 0.25 if rule1_satisfied else 0.0
    rule2_1_score = 0.75 if rule2_1_satisfied else 0.0
    rule2_2_score = 0.75 if rule2_2_satisfied else 0.0

    total_score = rule1_score + max(rule2_1_score, rule2_2_score)

    return {
        "query": QUERY,
        "id": TASK_ID,
        "path": path,
        "steprules": STEPRULES,
        "total_score": total_score,
        "details": details,
        "rejection_reason": None
    }


if __name__ == "__main__":
    paths = [
        "BMK/first/6511b9bb",
        "BMK/2026-04-29/qq/BMK评测/746957d5-f9ff-4aae-8f60-f065efddc07b",
        "BMK/second/3c9efa72",
        "BMK/third/60ff1fa0",
        "BMK/fourth/a09705ab"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
