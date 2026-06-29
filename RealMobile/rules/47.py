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


QUERY = "我只有 200 块钱的预算，但是今天想在北京体验一把老钱风或者富豪的一天。请去小红书或者抖音帮我挖掘一些低成本甚至免费的奢华体验（比如免费看高端画展、去五星级酒店大堂喝杯最便宜的咖啡蹭环境等）。帮我把这些地点用高德地图串成一条路线，然后去微博发一条装腔作势的预告动态"
TASK_ID = 47
STEPRULES = """分段评分规则（6阶段）

1. 打开小红书或抖音 → 总分:0.167

2. 搜索低成本奢华体验 → 总分:0.334

3. 收集地点信息 → 总分:0.5

4. 打开高德地图 → 总分:0.667

5. 规划路线 → 总分:0.834

6. 在微博发布预告动态 → 总分:1.0

一票否决条件：
- 未打开小红书或抖音 → 分数:0
- 未打开高德地图 → 分数:0
- 未打开微博 → 分数:0"""


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
    social_app_found = False
    map_found = False
    weibo_found = False

    for xml_string in xml_strings:
        if not social_app_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs') or contains(@package, 'aweme') or contains(@package, 'douyin')]", {})
                if match_flag == 1:
                    social_app_found = True
            except:
                pass

        if not map_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'minimap')]", {})
                if match_flag == 1:
                    map_found = True
            except:
                pass

        if not weibo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'weibo')]", {})
                if match_flag == 1:
                    weibo_found = True
            except:
                pass

    if not social_app_found:
        return True, "未打开小红书或抖音"

    if not map_found:
        return True, "未打开高德地图"

    if not weibo_found:
        return True, "未打开微博"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书或抖音"""
    rule1_xpath = "//*[contains(@package, 'xhs') or contains(@package, 'aweme') or contains(@package, 'douyin')]"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule1_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书或抖音"

    return False, "未打开小红书或抖音"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：搜索低成本奢华体验"""
    rule2_xpaths = [
        "//*[contains(@text, '搜索') or contains(@text, '搜') or contains(@ocr_texts, '搜索')]",
        "//*[contains(@text, '奢华') or contains(@text, '体验') or contains(@text, '免费') or contains(@text, '低成本') or contains(@ocr_texts, '奢华') or contains(@ocr_texts, '体验')]",
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

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索低成本奢华体验"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未搜索奢华体验"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：收集地点信息"""
    rule3_xpaths = [
        "//*[contains(@text, '地点') or contains(@text, '地址') or contains(@text, '酒店') or contains(@text, '画展') or contains(@ocr_texts, '地点') or contains(@ocr_texts, '地址')]",
        "//*[contains(@text, '北京') or contains(@text, '五星') or contains(@text, '咖啡') or contains(@ocr_texts, '北京') or contains(@ocr_texts, '五星')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 收集地点信息"

    return False, "未收集地点信息"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开高德地图"""
    rule4_xpath = "//*[contains(@package, 'minimap')]"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule4_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开高德地图"

    return False, "未打开高德地图"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：规划路线"""
    rule5_xpaths = [
        "//*[contains(@package, 'minimap') and contains(@text, '添加途经点')] and //*[contains(@text, '北京')] and //*[contains(@class, 'EditText')]",
    ]

    checked = [False] * len(rule5_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(rule5_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule5_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 规划路线"

    return False, "未规划路线"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：在微博发布预告动态"""
    rule6_xpaths = [
        "//*[contains(@package, 'weibo')]",
        "//*[(contains(@text, '发布') or contains(@text, '发送') or contains(@text, '分享') or contains(@ocr_texts, '发布') or contains(@ocr_texts, '发送')) and bbox_contains_point(@bounds, $point)]",
    ]

    checked = [False] * len(rule6_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(rule6_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule6_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 在微博发布动态"

    return False, "未在微博发布动态"


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
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)
    rule5_satisfied, rule5_evidence = evaluate_rule_5(xml_strings, actions)
    rule6_satisfied, rule6_evidence = evaluate_rule_6(xml_strings, actions)

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
        rule4_satisfied = False
        rule5_satisfied = False
        rule6_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False
        rule4_satisfied = False
        rule5_satisfied = False
        rule6_satisfied = False
    elif not rule3_satisfied:
        rule4_satisfied = False
        rule5_satisfied = False
        rule6_satisfied = False
    elif not rule4_satisfied:
        rule5_satisfied = False
        rule6_satisfied = False
    elif not rule5_satisfied:
        rule6_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.167
    if rule2_satisfied:
        max_score = 0.334
    if rule3_satisfied:
        max_score = 0.5
    if rule4_satisfied:
        max_score = 0.667
    if rule5_satisfied:
        max_score = 0.834
    if rule6_satisfied:
        max_score = 1.0

    details = [
        {"rule": "1. 打开小红书或抖音", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 搜索低成本奢华体验", "score": 0.334, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 收集地点信息", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 打开高德地图", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 规划路线", "score": 0.834, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 在微博发布预告动态", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/3c89717b",
        "BMK/second/27b802d2",
        "BMK/third/3537fc2c",
        "BMK/fourth/c5370962"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
