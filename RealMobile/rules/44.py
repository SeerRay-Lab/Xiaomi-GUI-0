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


QUERY = "分别去高德、携程上看看周六五道口全季酒店的价格，把相关权益信息总结给我，然后比较一下权益最好的平台订一个大床房"
TASK_ID = 44
STEPRULES = """分段评分规则（6阶段）

1. 打开高德和携程 → 总分:0.167

2. 查看五道口全季酒店信息 → 总分:0.334

3. 查看酒店价格信息 → 总分:0.5

4. 查看权益信息 → 总分:0.667

5. 比较权益并选择最好的平台 → 总分:0.834

6. 订大床房 → 总分:1.0

一票否决条件：
- 未打开高德和携程 → 分数:0
- 未查看酒店信息 → 分数:0
- 未订房 → 分数:0"""


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
    platform_found = False
    hotel_found = False
    booking_found = False

    for xml_string in xml_strings:
        if not platform_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'minimap') or contains(@package, 'ctrip')]", {})
                if match_flag == 1:
                    platform_found = True
            except:
                pass

        if not hotel_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '全季') or contains(@text, '酒店') or contains(@text, '五道口') or contains(@ocr_texts, '全季') or contains(@ocr_texts, '酒店')]", {})
                if match_flag == 1:
                    hotel_found = True
            except:
                pass

        if not booking_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '预订') or contains(@text, '订房') or contains(@text, '立即预订') or contains(@text, '大床房') or contains(@ocr_texts, '预订') or contains(@ocr_texts, '大床房')]", {})
                if match_flag == 1:
                    booking_found = True
            except:
                pass

    if not platform_found:
        return True, "未打开高德和携程"

    if not hotel_found:
        return True, "未查看酒店信息"

    if not booking_found:
        return True, "未订房"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开高德和携程"""
    rule1_xpaths = [
        "//*[contains(@package, 'minimap')  ]",
        "//*[contains(@package, 'ctrip')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开高德和携程"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开平台"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：查看五道口全季酒店信息"""
    rule2_xpaths = [
        "//*[contains(@package, 'ctrip') and contains(@text, '全季')] and //*[contains(@text, '五道口')]",
        "//*[contains(@package, 'ctrip') and (contains(@text, '周六') or contains(@ocr_texts, '周六'))]" ,
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看五道口全季酒店信息"

    if any(checked):
        print(checked)
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未查看酒店信息"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：查看酒店价格信息"""
    rule3_xpaths = [
        "//*[contains(@package, 'minimap') and contains(@text, '全季')] and //*[contains(@text, '五道口')]",
        "//*[contains(@package, 'minimap') and contains(@text, '周六')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看酒店价格信息"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未查看价格信息"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：查看权益信息"""
    rule4_xpaths = [
        "//*[contains(@text, '权益') or contains(@text, '优惠') or contains(@text, '服务') or contains(@text, '便利') or contains(@ocr_texts, '权益') or contains(@ocr_texts, '优惠')]",
        "//*[contains(@text, '包含') or contains(@text, '赠送') or contains(@text, '免费') or contains(@ocr_texts, '包含') or contains(@ocr_texts, '免费')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看权益信息"

    return False, "未查看权益信息"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：比较权益并选择最好的平台"""
    rule5_xpaths = [
        "//*[contains(@text, '高德') or contains(@text, '携程') or contains(@text, '比较') or contains(@ocr_texts, '高德') or contains(@ocr_texts, '携程')]",
        "//*[contains(@text, '权益') or contains(@text, '优惠') or contains(@text, '最好') or contains(@ocr_texts, '权益') or contains(@ocr_texts, '优惠')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 比较权益并选择平台"

    return False, "未比较权益"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：订大床房"""
    rule6_xpaths = [
        "//*[contains(@text, '大床房') or contains(@text, '双床房') or contains(@text, '房型') or contains(@ocr_texts, '大床房') or contains(@ocr_texts, '房型')]",
        "//*[(contains(@text, '预订') or contains(@text, '立即预订') or contains(@text, '订房') or contains(@ocr_texts, '预订') or contains(@ocr_texts, '订房')) and bbox_contains_point(@bounds, $point)]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 订大床房"

    return False, "未订房"


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
        {"rule": "1. 打开高德和携程", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 查看五道口全季酒店信息", "score": 0.334, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 查看酒店价格信息", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 查看权益信息", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 比较权益并选择平台", "score": 0.834, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 订大床房", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/38e06852",
        "BMK/second/60c04d83",
        "BMK/third/7325f1bf",
        "BMK/fourth/57cded11"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
