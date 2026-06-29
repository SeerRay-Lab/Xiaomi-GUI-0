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


QUERY = "我要从北京去上海。在携程里分别搜索明天的高铁票和机票，对比一下这两种交通方式，看看那个最早能到上海，把最早到达的那个车次或航班号发给qq我的电脑"
TASK_ID = 93
STEPRULES = """分段评分规则（6阶段）

1. 打开携程搜索高铁 → 总分:0.167

2. 查看高铁最早到达时间 → 总分:0.333

3. 搜索机票 → 总分:0.5

4. 查看机票最早到达时间 → 总分:0.667

5. 比较并选出最早的 → 总分:0.833

6. 通过QQ发送 → 总分:1.0

一票否决条件：
- 未打开携程 → 分数:0
- 未对比两种交通方式 → 分数:0"""


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
    ctrip_found = False
    comparison_found = False

    for xml_string in xml_strings:
        if not ctrip_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'ctrip')]", {})
                if match_flag == 1:
                    ctrip_found = True
            except:
                pass

        if not comparison_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '高铁') or contains(@text, '机票') or contains(@text, '对比') or contains(@ocr_texts, '高铁') or contains(@ocr_texts, '机票') or contains(@ocr_texts, '对比')]", {})
                if match_flag == 1:
                    comparison_found = True
            except:
                pass

    if not ctrip_found:
        return True, "未打开携程"

    if not comparison_found:
        return True, "未对比两种交通方式"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开携程搜索高铁"""
    rule1_xpaths = [
        "//*[contains(@package, 'ctrip')]",
        "//*[contains(@text, '北京') and contains(@resource-id, 'depart_station')] and //*[contains(@text, '上海') and contains(@resource-id, 'arrive_station')] and //*[contains(@text, '明天')]",
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

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开携程搜索高铁"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未搜索高铁"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：查看高铁最早到达时间"""
    rule2_xpaths = [
        "//*[contains(@text, '最早') or contains(@text, '到达') or contains(@text, '时间') or contains(@text, '高铁') or contains(@ocr_texts, '最早') or contains(@ocr_texts, '到达')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看高铁时间"

    return False, "未查看高铁信息"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：搜索机票"""
    rule3_xpaths = [
        "//*[contains(@text, '北京')] and //*[contains(@text, '上海')] and //*[contains(@text, '经济舱')]  and //*[contains(@resource-id, '航班')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索机票"

    return False, "未搜索机票"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：查看机票最早到达时间"""
    rule4_xpaths = [
        "//*[contains(@text, '最早') or contains(@text, '到达') or contains(@text, '时间') or contains(@text, '机票') or contains(@ocr_texts, '最早') or contains(@ocr_texts, '到达')]",
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
            except:
                pass

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 查看机票时间"

    return False, "未查看机票信息"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：比较并选出最早的"""
    rule5_xpaths = [
        "//*[contains(@text, '对比') or contains(@text, '比较') or contains(@text, '最早') or contains(@text, '车次') or contains(@text, '航班') or contains(@ocr_texts, '对比') or contains(@ocr_texts, '比较')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 比较选出最早"

    return False, "未比较选择"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：通过QQ发送"""
    rule6_xpaths = [
        "//*[contains(@package, 'mobileqq')]",
        "//*[contains(@text, '我的电脑')] and //*[contains(@text, '发送') and bbox_contains_point(@bounds, $point)]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 通过QQ发送"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule6_xpaths)}"

    return False, "未发送QQ"


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
        {"rule": "1. 打开携程搜索高铁", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 查看高铁最早到达时间", "score": 0.333, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 搜索机票", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 查看机票最早到达时间", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 比较并选出最早的", "score": 0.833, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 通过QQ发送", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/eab902b1",
        "BMK/second/3c00f8c7",
        "BMK/third/ce6e89ea",
        "BMK/fourth/8fb63142"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
