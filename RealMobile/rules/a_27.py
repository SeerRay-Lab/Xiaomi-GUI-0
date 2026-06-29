import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "我现在有3克黄金，帮我算一下以现在的金价是否能够购买淘宝苹果旗舰店最新的苹果手机"
TASK_ID = 27
STEPRULES = """评分规则

1. 查询当前金价 → 总分:0.5

2. 在淘宝苹果旗舰店找到最新苹果手机的价格 → 总分:1.0"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
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

    return xml_strings, actions, steps




def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：查询当前金价"""
    rule1_xpaths = [
        "//*[contains(@text, '金价') or contains(@text, '黄金') or contains(@text, '金')]",
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '价格')]",
        "//*[contains(@text, '克') or contains(@text, '每克') or contains(@text, '克价')]",
        "//*[contains(@text, '今天') or contains(@text, '今日') or contains(@text, '实时') or contains(@text, '当前')]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule1_xpaths)):
            xpath = rule1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    continue
            except:
                pass

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 查询到当前金价"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未查询到金价"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：在淘宝苹果旗舰店找到最新苹果手机的价格"""
    rule2_xpaths = [
        "//*[contains(@package, 'taobao') or contains(@text, '淘宝')]",
        "//*[contains(@text, '苹果') and contains(@text, '旗舰店')]",
        "//*[contains(@text, 'iPhone') or contains(@text, '苹果手机')]",
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '价格')]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule2_xpaths)):
            xpath = rule2_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    continue
            except:
                pass

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 找到苹果手机价格"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未找到苹果手机价格"




def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 27,
            "path": "...",
            "steprules": "...",
            "total_score": 1.0,
            "details": [...]
        }
    """
    try:
        xml_strings, actions, steps = load_trajectory_data(path)
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

    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)

    if not rule1_satisfied:
        rule2_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.5
    if rule2_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 查询当前金价",
            "score": 0.5,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 找到苹果手机价格",
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
    result = evaluate_trajectory(path="BMK/2026-04-29/淘宝/BMK评测/5bbc50b7-8bdf-4ed2-b78c-baf9dfa2659d")
    print(json.dumps(result, ensure_ascii=False, indent=2))
