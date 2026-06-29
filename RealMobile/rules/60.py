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


QUERY = "我预算500块钱，帮我看看b站、腾讯视频、qq音乐、汽水音乐、盒马的年会员总共多少钱，我最多可以开通几个app的年会员"
TASK_ID = 60
STEPRULES = """分段评分规则（5阶段）

1. 打开各应用查看年会员价格 → 总分:0.2

2. 查看B站、腾讯视频的年会员价格 → 总分:0.4

3. 查看QQ音乐、汽水音乐、盒马的年会员价格 → 总分:0.6

4. 计算五个应用的年会员总价 → 总分:0.8

5. 计算最多可以开通几个年会员（基于500元预算） → 总分:1.0

一票否决条件：
- 未打开B站 → 分数:0
- 未打开腾讯视频 → 分数:0
- 未打开QQ音乐 → 分数:0
- 未打开汽水音乐 → 分数:0
- 未打开盒马 → 分数:0"""


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
    bili_found = False
    qqlive_found = False
    qqmusic_found = False
    luna_found = False
    hippo_found = False

    for xml_string in xml_strings:
        if not bili_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'bili')]", {})
                if match_flag == 1:
                    bili_found = True
            except:
                pass

        if not qqlive_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'qqlive')]", {})
                if match_flag == 1:
                    qqlive_found = True
            except:
                pass

        if not qqmusic_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'qqmusic')]", {})
                if match_flag == 1:
                    qqmusic_found = True
            except:
                pass

        if not luna_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'luna.music')]", {})
                if match_flag == 1:
                    luna_found = True
            except:
                pass

        if not hippo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'hippo')]", {})
                if match_flag == 1:
                    hippo_found = True
            except:
                pass

    if not bili_found:
        return True, "未打开B站"

    if not qqlive_found:
        return True, "未打开腾讯视频"

    if not qqmusic_found:
        return True, "未打开QQ音乐"

    if not luna_found:
        return True, "未打开汽水音乐"

    if not hippo_found:
        return True, "未打开盒马"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开各应用查看年会员价格"""
    rule1_xpaths = [
        "//*[contains(@package, 'bili')] | //*[contains(@package, 'qqlive')] | //*[contains(@package, 'qqmusic')] | //*[contains(@package, 'luna.music')] | //*[contains(@package, 'hippo')]",
        "//*[contains(@text, '年会员') or contains(@text, '会员') or contains(@text, '年度') or contains(@ocr_texts, '年会员') or contains(@ocr_texts, '会员')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开应用查看年会员"

    return False, "未查看年会员"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：查看B站、腾讯视频的年会员价格"""
    rule2_xpaths = [
        "//*[contains(@package, 'bili') ] and //*[contains(@text, '年') or contains(@ocr_texts, '年')] and //*[contains(@text, '会员') or contains(@ocr_texts, '会员')]",
        "//*[contains(@package, 'qqlive')] and //*[contains(@text, '年') or contains(@ocr_texts, '年')] and //*[contains(@text, '会员') or contains(@ocr_texts, '会员')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看B站和腾讯视频价格"
    
    print(checked)

    return False, "未查看B站和腾讯视频价格"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：查看QQ音乐、汽水音乐、盒马的年会员价格"""
    rule3_xpaths = [
        "//*[contains(@package, 'qqmusic')] and //*[contains(@text, '年') or contains(@ocr_texts, '年')] and //*[contains(@text, '会员') or contains(@ocr_texts, '会员')]",
        "//*[contains(@package, 'luna.music')] and //*[contains(@text, '年') or contains(@ocr_texts, '年')] and //*[contains(@text, '会员') or contains(@ocr_texts, '会员')]",
        "//*[contains(@package, 'hippo')] and //*[contains(@text, '年') or contains(@ocr_texts, '年')] and //*[contains(@text, '会员') or contains(@ocr_texts, '会员')]",
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

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 查看QQ音乐、汽水音乐、盒马价格"

    print(checked)
    return False, "未查看其他应用价格"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：计算五个应用的年会员总价"""
    rule4_xpaths = [
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '价格') or contains(@ocr_texts, '¥') or contains(@ocr_texts, '元')]",
        "//*[contains(@text, '总') or contains(@text, '合计') or contains(@text, '计算') or contains(@ocr_texts, '总') or contains(@ocr_texts, '合计')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 计算年会员总价"

    return False, "未计算总价"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：计算最多可以开通几个年会员（基于500元预算）"""
    rule5_xpaths = [
        "//*[contains(@text, '500') or contains(@text, '预算') or contains(@text, '最多') or contains(@ocr_texts, '500') or contains(@ocr_texts, '预算')]",
        "//*[contains(@text, '开通') or contains(@text, '个数') or contains(@text, '可以') or contains(@ocr_texts, '开通') or contains(@ocr_texts, '个数')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 计算可开通的年会员个数"

    return False, "未计算年会员个数"


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

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
        rule4_satisfied = False
        rule5_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False
        rule4_satisfied = False
        rule5_satisfied = False
    elif not rule3_satisfied:
        rule4_satisfied = False
        rule5_satisfied = False
    elif not rule4_satisfied:
        rule5_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.2
    if rule2_satisfied:
        max_score = 0.4
    if rule3_satisfied:
        max_score = 0.6
    if rule4_satisfied:
        max_score = 0.8
    if rule5_satisfied:
        max_score = 1.0

    details = [
        {"rule": "1. 打开各应用查看年会员价格", "score": 0.2, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 查看B站、腾讯视频的年会员价格", "score": 0.4, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 查看QQ音乐、汽水音乐、盒马的年会员价格", "score": 0.6, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 计算五个应用的年会员总价", "score": 0.8, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 计算最多可以开通几个年会员", "score": 1.0, "satisfied": rule5_satisfied, "evidence": rule5_evidence}
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
        "BMK/first/63fc7190",
        "BMK/second/a595e42b",
        "BMK/third/a90c95fd",
        "BMK/fourth/0efd1c1b"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
