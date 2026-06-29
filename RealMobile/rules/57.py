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


QUERY = "小红书搜索佛跳墙的做法，浏览几个帖子总结一下三件核心原料，帮我在盒马将这些原材料加入购物车，算一下需要的价格，然后去抖音看一下我直接买一份佛跳墙哪个更合适"
TASK_ID = 57
STEPRULES = """分段评分规则（6阶段）

1. 打开小红书 → 总分:0.167

2. 搜索佛跳墙的做法并浏览帖子 → 总分:0.333

3. 总结三件核心原料 → 总分:0.5

4. 打开盒马并加入购物车 → 总分:0.667

5. 计算价格 → 总分:0.833

6. 打开抖音查看成品价格 → 总分:1.0

一票否决条件：
- 未打开小红书 → 分数:0
- 未搜索佛跳墙做法 → 分数:0
- 未打开盒马 → 分数:0
- 未打开抖音 → 分数:0"""


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
    xhs_found = False
    buddha_found = False
    hippo_found = False
    douyin_found = False

    for xml_string in xml_strings:
        if not xhs_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs')]", {})
                if match_flag == 1:
                    xhs_found = True
            except:
                pass

        if not buddha_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '佛跳墙') or contains(@text, '做法') or contains(@ocr_texts, '佛跳墙') or contains(@ocr_texts, '做法')]", {})
                if match_flag == 1:
                    buddha_found = True
            except:
                pass

        if not hippo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'hippo')]", {})
                if match_flag == 1:
                    hippo_found = True
            except:
                pass

        if not douyin_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'aweme')]", {})
                if match_flag == 1:
                    douyin_found = True
            except:
                pass

    if not xhs_found:
        return True, "未打开小红书"

    if not buddha_found:
        return True, "未搜索佛跳墙做法"

    if not hippo_found:
        return True, "未打开盒马"

    if not douyin_found:
        return True, "未打开抖音"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书"""
    rule1_xpath = "//*[contains(@package, 'xhs')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书"

    return False, "未打开小红书"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：搜索佛跳墙的做法并浏览帖子"""
    rule2_xpaths = [
        "//*[contains(@package, 'xhs') and contains(@text, '佛跳墙')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索佛跳墙做法并浏览帖子"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未搜索佛跳墙做法"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：总结三件核心原料"""
    rule3_xpaths = [
        "//*[contains(@text, '原料') or contains(@text, '材料') or contains(@text, '配方') or contains(@ocr_texts, '原料') or contains(@ocr_texts, '材料') or contains(@ocr_texts, '配方')]",
        "//*[contains(@text, '鸡') or contains(@text, '海参') or contains(@text, '冬菇') or contains(@text, '瑶柱') or contains(@ocr_texts, '鸡') or contains(@ocr_texts, '海参') or contains(@ocr_texts, '冬菇')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 总结核心原料"

    return False, "未总结原料"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开盒马并加入购物车"""
    rule4_xpaths = [
        "//*[(contains(@content-desc, '加入购物车') or contains(@text, '加入购物车')) and bbox_contains_point(../@bounds, $point)]",
        "//*[(contains(@content-desc, '加入购物车') or contains(@text, '加入购物车')) and bbox_contains_point(../@bounds, $point)]",
        "//*[(contains(@content-desc, '加入购物车') or contains(@text, '加入购物车')) and bbox_contains_point(../@bounds, $point)]",
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(rule4_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule4_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    break
            except:
                pass

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开盒马并加入购物车"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未在盒马加入购物车"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：计算价格"""
    rule5_xpaths = [
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '价格') or contains(@ocr_texts, '¥') or contains(@ocr_texts, '价格')]",
        "//*[contains(@text, '总计') or contains(@text, '合计') or contains(@text, '需要') or contains(@ocr_texts, '总计') or contains(@ocr_texts, '合计')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 计算价格"

    return False, "未计算价格"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：打开抖音查看成品价格"""
    rule6_xpaths = [
        "//*[contains(@package, 'aweme') and contains(@text, '佛跳墙')] and  //*[contains(@text, '¥') or contains(@ocr_texts, '¥') or contains(@text, '已售')  or contains(@ocr_texts, '已售') ]",
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

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开抖音查看成品"

    return False, "未打开抖音查看成品"


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
        max_score = 0.333
    if rule3_satisfied:
        max_score = 0.5
    if rule4_satisfied:
        max_score = 0.667
    if rule5_satisfied:
        max_score = 0.833
    if rule6_satisfied:
        max_score = 1.0

    details = [
        {"rule": "1. 打开小红书", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 搜索佛跳墙的做法并浏览帖子", "score": 0.333, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 总结三件核心原料", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 打开盒马并加入购物车", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 计算价格", "score": 0.833, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 打开抖音查看成品价格", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/5d1855a2",
        "BMK/second/4075ef2e",
        "BMK/third/84bddc49",
        "BMK/fourth/a542395e"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
