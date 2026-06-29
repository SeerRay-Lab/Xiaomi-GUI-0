import json
import os
import sys
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "高德地图看一下北京颐和园去大兴机场哪种交通方式耗时最短"
TASK_ID = 87
STEPRULES = """分段评分规则（3阶段）

1. 打开高德地图 → 总分:0.333

2. 搜索颐和园和大兴机场的路线 → 总分:0.667

3. 查看不同交通方式并找出最短耗时 → 总分:1.0

一票否决条件：
- 未打开高德地图 → 分数:0
- 未搜索路线 → 分数:0"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """加载轨迹数据，优先使用 _ocr.xml，并正确计算实际点击坐标"""
    task_json_path = os.path.join(path, "task.json")
    with open(task_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    steps = data.get('data', data.get('steps', []))
    xml_strings = []
    actions = []

    for step in steps:
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


def extract_text_content(xml_string: str) -> str:
    """从XML中提取所有文本内容用于检查"""
    try:
        root = ET.fromstring(xml_string)
        texts = []
        for elem in root.iter():
            text = elem.get('text', '')
            ocr_texts = elem.get('ocr_texts', '')
            if text:
                texts.append(text)
            if ocr_texts:
                texts.append(ocr_texts)
        return ' '.join(texts)
    except:
        return ""


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    amap_found = False
    route_found = False

    for xml_string in xml_strings:
        if not amap_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'minimap')]", {})
                if match_flag == 1:
                    amap_found = True
            except:
                pass

        if not route_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '颐和园') or contains(@text, '大兴机场') or contains(@text, '路线') or contains(@text, '起点') or contains(@ocr_texts, '颐和园') or contains(@ocr_texts, '大兴机场')]", {})
                if match_flag == 1:
                    route_found = True
            except:
                pass

    if not amap_found:
        return True, "未打开高德地图"

    if not route_found:
        return True, "未搜索路线"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开高德地图"""
    rule1_xpaths = [
        "//*[contains(@package, 'minimap')]",
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

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

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开高德地图"

    return False, "未打开高德地图"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：搜索颐和园和大兴机场的路线"""
    rule2_xpaths = [
        "//*[contains(@text, '颐和园') and contains(@resource-id, 'summary_start')] and //*[contains(@text, '大兴') and contains(@text, '机场') and contains(@resource-id, 'summary_end')] ",
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

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

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索路线"

    return False, "未搜索路线"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：查看不同交通方式并找出最短耗时"""
    rule3_xpaths = [
        "//*[contains(@text, '驾车') or contains(@text, '公共交通') or contains(@text, '地铁') or contains(@text, '耗时') or contains(@text, '分钟') or contains(@ocr_texts, '驾车') or contains(@ocr_texts, '公交') or contains(@ocr_texts, '耗时')]",
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(rule3_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule3_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 查看交通方式耗时"

    return False, "未查看交通方式"


def evaluate_trajectory(path: str) -> dict:
    """参数：path: 轨迹目录路径"""
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
            "rejection_reason": f"无法加载轨迹数据: {str(e)}"
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

    veto_triggered, veto_reason = check_veto_conditions(xml_strings, actions)
    if veto_triggered:
        return {
            "query": QUERY,
            "id": TASK_ID,
            "path": path,
            "steprules": STEPRULES,
            "total_score": 0.0,
            "details": [],
            "rejection_reason": veto_reason
        }

    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.333
    if rule2_satisfied:
        max_score = 0.667
    if rule3_satisfied:
        max_score = 1.0

    details = [
        {"rule": "1. 打开高德地图", "score": 0.333, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 搜索颐和园和大兴机场的路线", "score": 0.667, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 查看不同交通方式并找出最短耗时", "score": 1.0, "satisfied": rule3_satisfied, "evidence": rule3_evidence}
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
    test_paths = [
        "BMK/first/d5b84f5b",
        "BMK/second/beb3ccd7",
        "BMK/third/d752c468",
        "BMK/fourth/90f9ed3c"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
