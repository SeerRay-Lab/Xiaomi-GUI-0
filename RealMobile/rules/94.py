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


QUERY = "打开高德地图，搜索从颐和园东宫门到北京首都机场的地铁预估时间，然后去微博发一条仅自己可见的动态，内容为去机场大概需要xx分钟"
TASK_ID = 94
STEPRULES = """分段评分规则（5阶段）

1. 打开高德地图搜索路线 → 总分:0.2

2. 查看地铁预估时间 → 总分:0.4

3. 打开微博 → 总分:0.6

4. 发表动态 → 总分:0.8

5. 设置为仅自己可见 → 总分:1.0

一票否决条件：
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
    amap_found = False
    weibo_found = False

    for xml_string in xml_strings:
        if not amap_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'minimap')]", {})
                if match_flag == 1:
                    amap_found = True
            except:
                pass

        if not weibo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'weibo')]", {})
                if match_flag == 1:
                    weibo_found = True
            except:
                pass

    if not amap_found:
        return True, "未打开高德地图"

    if not weibo_found:
        return True, "未打开微博"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开高德地图搜索路线"""
    rule1_xpaths = [
        "//*[contains(@package, 'minimap')]",
        "//*[contains(@text, '颐和园') or contains(@text, '机场') or contains(@text, '路线') or contains(@text, '搜索') or contains(@ocr_texts, '颐和园') or contains(@ocr_texts, '机场')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开高德地图搜索"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未搜索路线"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：查看地铁预估时间"""
    rule2_xpaths = [
        "//*[contains(@text, '公共交通')  and contains(@selected, 'true')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看地铁时间"

    return False, "未查看地铁信息"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开微博"""
    rule3_xpaths = [
        "//*[contains(@package, 'weibo')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开微博"

    return False, "未打开微博"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：发表动态"""
    rule4_xpaths = [
        "//*[contains(@text, '分钟') or contains(@text, '小时')] and //*[(contains(@text, '发布') or contains(@text, '发送') )  and bbox_contains_point(../@bounds, $point) ]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 发表动态"

    return False, "未发表动态"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：设置为仅自己可见"""
    rule5_xpaths = [
        "//*[contains(@text, '仅自己可见')  and bbox_contains_point(../@bounds, $point) ]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 设置隐私"

    return False, "未设置隐私"


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
        {"rule": "1. 打开高德地图搜索路线", "score": 0.2, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 查看地铁预估时间", "score": 0.4, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 打开微博", "score": 0.6, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 发表动态", "score": 0.8, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 设置为仅自己可见", "score": 1.0, "satisfied": rule5_satisfied, "evidence": rule5_evidence}
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
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a70c34cc",
        "BMK/first/ec48cb60",
        "BMK/second/698d8fbc",
        "BMK/third/446885c8",
        "BMK/fourth/45445d22"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
