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


QUERY = "在小红书搜索今年秋季流行的老钱风穿搭，浏览前两篇高赞图文，总结一下老钱风在颜色搭配和面料选择上的核心特点。记住这些主观特点，然后打开得物，根据你的总结，搜索并挑选一件最符合该风格的女装毛衣，加入我想要"
TASK_ID = 45
STEPRULES = """分段评分规则（6阶段）

1. 打开小红书 → 总分:0.167

2. 搜索老钱风穿搭 → 总分:0.334

3. 浏览高赞图文并总结特点 → 总分:0.5

4. 打开得物 → 总分:0.667

5. 搜索女装毛衣 → 总分:0.834

6. 加入我想要 → 总分:1.0

一票否决条件：
- 未打开小红书 → 分数:0
- 未搜索老钱风穿搭 → 分数:0
- 未打开得物 → 分数:0"""


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
    search_found = False
    duapp_found = False

    for xml_string in xml_strings:
        if not xhs_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs')]", {})
                if match_flag == 1:
                    xhs_found = True
            except:
                pass

        if not search_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '老钱风') or contains(@text, '穿搭') or contains(@text, '秋季') or contains(@ocr_texts, '老钱风') or contains(@ocr_texts, '穿搭')]", {})
                if match_flag == 1:
                    search_found = True
            except:
                pass

        if not duapp_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'duapp')]", {})
                if match_flag == 1:
                    duapp_found = True
            except:
                pass

    if not xhs_found:
        return True, "未打开小红书"

    if not search_found:
        return True, "未搜索老钱风穿搭"

    if not duapp_found:
        return True, "未打开得物"

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
    """规则2：搜索老钱风穿搭"""
    rule2_xpaths = [
        "//*[contains(@text, '搜索') or contains(@text, '搜') or contains(@ocr_texts, '搜索')]",
        "//*[contains(@text, '老钱风') or contains(@text, '穿搭') or contains(@text, '秋季') or contains(@ocr_texts, '老钱风') or contains(@ocr_texts, '穿搭')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索老钱风穿搭"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未搜索老钱风穿搭"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：浏览高赞图文并总结特点"""
    rule3_xpaths = [
        "//*[contains(@text, '赞') or contains(@text, '点赞') or contains(@text, '高赞') or contains(@ocr_texts, '赞') or contains(@ocr_texts, '高赞')]",
        "//*[contains(@text, '老钱风') or contains(@text, '颜色') or contains(@text, '面料') or contains(@text, '穿搭') or contains(@ocr_texts, '老钱风') or contains(@ocr_texts, '颜色') or contains(@ocr_texts, '面料')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 浏览高赞图文"

    return False, "未浏览高赞图文"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开得物"""
    rule4_xpath = "//*[contains(@package, 'duapp')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开得物"

    return False, "未打开得物"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：搜索女装毛衣"""
    rule5_xpaths = [
        "//*[contains(@text, '搜索') or contains(@text, '搜') or contains(@ocr_texts, '搜索')]",
        "//*[contains(@text, '毛衣') or contains(@text, '女装') or contains(@text, '女') or contains(@ocr_texts, '毛衣') or contains(@ocr_texts, '女装')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索女装毛衣"

    return False, "未搜索毛衣"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：加入我想要"""
    rule6_xpaths = [
        "//*[(contains(@text, '我想要') or contains(@text, '加入') or contains(@text, '收藏') or contains(@ocr_texts, '我想要') or contains(@ocr_texts, '加入')) and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '我想要') or contains(@text, '已加入') or contains(@ocr_texts, '我想要')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 加入我想要"

    return False, "未加入我想要"


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
        {"rule": "1. 打开小红书", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 搜索老钱风穿搭", "score": 0.334, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 浏览高赞图文并总结特点", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 打开得物", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 搜索女装毛衣", "score": 0.834, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 加入我想要", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/39a58942",
        "BMK/second/4c25d1fd",
        "BMK/third/9767af67",
        "BMK/fourth/1fa7f1e6"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
