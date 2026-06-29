import json
import os
import sys
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "看一下携程明天早上北京到上海最早的航班，把航班号和起飞时间发送到QQ我的电脑"
TASK_ID = 25
STEPRULES = """分段评分规则（5阶段）

1. 打开携程 → 总分:0.2

2. 选择出发地（北京）和目的地（上海） → 总分:0.4

3. 选择日期时间（明天早上） → 总分:0.6

4. 找到航班信息 → 总分:0.8

5. 发送航班号和起飞时间到QQ我的电脑 → 总分:1.0

一票否决条件：
- 未打开携程 → 分数:0
- 出发地或目的地设置错误 → 分数:0
- 日期或时间设置不符合要求 → 分数:0
- 未发送航班信息到QQ → 分数:0"""


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


def is_tomorrow_date(text: str) -> bool:
    """检查文本中是否包含明天的日期标识"""
    tomorrow_patterns = [r'明天', r'tomorrow']
    for pattern in tomorrow_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_morning_time(text: str) -> bool:
    """检查文本中是否包含早上的时间"""
    morning_patterns = [r'早上', r'早', r'morning']
    for pattern in morning_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    ctrip_found = False
    beijing_found = False
    shanghai_found = False
    tomorrow_found = False
    morning_found = False
    flight_found = False

    for xml_string in xml_strings:
        text_content = extract_text_content(xml_string)

        if not ctrip_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'ctrip')]", {})
                if match_flag == 1:
                    ctrip_found = True
            except:
                pass

        if not beijing_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '北京') or contains(@ocr_texts, '北京')]", {})
                if match_flag == 1:
                    beijing_found = True
            except:
                pass

        if not shanghai_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '上海') or contains(@ocr_texts, '上海')]", {})
                if match_flag == 1:
                    shanghai_found = True
            except:
                pass

        if not tomorrow_found and is_tomorrow_date(text_content):
            tomorrow_found = True

        if not morning_found and is_morning_time(text_content):
            morning_found = True

        if not flight_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '航班') or contains(@ocr_texts, '航班')]", {})
                if match_flag == 1:
                    flight_found = True
            except:
                pass

    if not ctrip_found:
        return True, "未打开携程"

    if not beijing_found or not shanghai_found:
        reason = "出发地或目的地设置错误"
        if not beijing_found:
            reason += "（未设置北京为出发地）"
        if not shanghai_found:
            reason += "（未设置上海为目的地）"
        return True, reason

    if not tomorrow_found or not morning_found:
        reason = "日期或时间设置不符合要求"
        if not tomorrow_found:
            reason += "（未设置明天）"
        if not morning_found:
            reason += "（未设置早上）"
        return True, reason

    if not flight_found:
        return True, "未找到航班信息"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开携程"""
    rule1_xpath = "//*[contains(@package, 'ctrip')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开携程"

    return False, "未打开携程"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：选择出发地（北京）和目的地（上海）"""
    rule2_xpaths = [
        "//*[contains(@text, '北京') or contains(@ocr_texts, '北京')]",
        "//*[contains(@text, '上海') or contains(@ocr_texts, '上海')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 选择北京和上海"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未设置出发地或目的地"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：选择日期时间（明天早上）"""
    evidence_steps = []
    tomorrow_found = False
    morning_found = False

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        text_content = extract_text_content(xml_string)

        if not tomorrow_found and is_tomorrow_date(text_content):
            tomorrow_found = True
            evidence_steps.append(i)

        if not morning_found and is_morning_time(text_content):
            morning_found = True
            evidence_steps.append(i)

    if tomorrow_found and morning_found:
        return True, f"步骤{sorted(set(evidence_steps))}: 选择明天早上"

    if tomorrow_found or morning_found:
        return False, f"部分条件满足: 明天{'是' if tomorrow_found else '否'}, 早上{'是' if morning_found else '否'}"

    return False, "未设置日期或时间"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：找到航班信息"""
    rule4_xpath = "//*[contains(@text, '航班') or contains(@ocr_texts, '航班')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 找到航班信息"

    return False, "未找到航班信息"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：发送航班号和起飞时间到QQ我的电脑"""
    flight_info = []
    for xml_string in xml_strings:
        text_content = extract_text_content(xml_string)
        flight_numbers = re.findall(r'[A-Z]{2}\d{3,4}', text_content)
        times = re.findall(r'\d{1,2}:\d{2}', text_content)
        flight_info.extend(flight_numbers)
        flight_info.extend(times)

    if not flight_info:
        return False, "未提取到航班号或起飞时间"

    qq_keyword = None
    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        try:
            root = ET.fromstring(xml_string)
            qq_found = False
            my_computer_found = False

            for elem in root.iter():
                package = elem.get('package', '')
                text = elem.get('text', '')

                if 'mobileqq' in package:
                    qq_found = True
                if '我的电脑' in text:
                    my_computer_found = True

            if qq_found and my_computer_found:
                for elem in root.iter():
                    elem_class = elem.get('class', '')
                    text = elem.get('text', '')
                    if 'EditText' in elem_class and text and len(text) > 1:
                        qq_keyword = text
                        break

            if qq_keyword:
                break
        except:
            pass

    if not qq_keyword:
        return False, "未找到QQ中发送的信息"

    keyword_parts = re.split(r'[\s《》<>、]+', qq_keyword)
    keyword_parts = [p for p in keyword_parts if p]

    matched = False
    for flight_item in flight_info:
        for keyword_part in keyword_parts:
            if flight_item in keyword_part or keyword_part in flight_item:
                matched = True
                break
        if matched:
            break

    if matched:
        evidence = f"发送信息: {qq_keyword}"
        return True, f"发送航班号和起飞时间到QQ我的电脑（{evidence}）"

    return False, f"发送的信息不包含航班号或起飞时间（发送: {qq_keyword}, 航班信息: {flight_info}）"


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
        {"rule": "1. 打开携程", "score": 0.2, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 选择出发地（北京）和目的地（上海）", "score": 0.4, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 选择日期时间（明天早上）", "score": 0.6, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 找到航班信息", "score": 0.8, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 发送航班号和起飞时间到QQ我的电脑", "score": 1.0, "satisfied": rule5_satisfied, "evidence": rule5_evidence}
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
        "BMK/first/c56bfa95",
        "BMK/2026-04-29/携程旅行_qq/BMK评测/5d5fbdc1-2adf-46bb-b4fe-531af963342d",
        "BMK/second/c5628dca",
        "BMK/third/f52e75a1",
        "BMK/fourth/0d1c7c9a"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
