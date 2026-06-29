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


QUERY = "请分别去抖音、得物、汽水音乐、小红书、微博五个App里查看各自的'客服热线电话号码'或者'消费者服务热线'。记住这些号码，然后打开QQ，以列表的形式将这些App的名字和对应的电话号码发给我的电脑"
TASK_ID = 41
STEPRULES = """分段评分规则（5阶段）

1. 打开多个APP查看客服电话 → 总分:0.2

2. 在APP中找到客服电话信息 → 总分:0.4

3. 记录五个APP的客服电话 → 总分:0.6

4. 打开QQ → 总分:0.8

5. 发送电话号码列表到电脑 → 总分:1.0

一票否决条件：
- 未打开任何APP查看客服电话 → 分数:0
- 未打开QQ → 分数:0
- 未找到客服电话 → 分数:0"""


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
    app_found = False
    phone_found = False
    qq_found = False

    for xml_string in xml_strings:
        if not app_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'aweme') or contains(@package, 'douyin') or contains(@package, 'duapp') or contains(@package, 'luna.music') or contains(@package, 'xhs') or contains(@package, 'weibo')]", {})
                if match_flag == 1:
                    app_found = True
            except:
                pass

        if not phone_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '客服') or contains(@text, '热线') or contains(@text, '电话') or contains(@text, '联系') or contains(@ocr_texts, '客服') or contains(@ocr_texts, '热线')]", {})
                if match_flag == 1:
                    phone_found = True
            except:
                pass

        if not qq_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'mobileqq')]", {})
                if match_flag == 1:
                    qq_found = True
            except:
                pass

    if not app_found:
        return True, "未打开任何APP查看客服电话"

    if not phone_found:
        return True, "未找到客服电话信息"

    if not qq_found:
        return True, "未打开QQ"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开多个APP查看客服电话"""
    rule1_xpaths = [
        "//*[contains(@package, 'aweme')] and //*[contains(@text, '客服') or contains(@text, '客户服务') or contains(@text, '电话')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开多个APP查看客服电话"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开APP查看客服电话"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：在APP中找到客服电话信息"""
    rule2_xpaths = [
        "//*[contains(@package, 'duapp')] and //*[contains(@text, '客服') or contains(@text, '客户服务') or contains(@text, '电话')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 在APP中找到客服电话信息"

    return False, "未找到客服电话信息"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：记录五个APP的客服电话"""
    rule3_xpaths = [
        "//*[contains(@package, 'luna.music')] and //*[contains(@text, '客服') or contains(@text, '客户服务') or contains(@text, '电话')]",
        "//*[contains(@package, 'xhs')] and //*[contains(@text, '客服') or contains(@text, '客户服务') or contains(@text, '电话')]",
        
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
        return True, f"步骤{sorted(set(evidence_steps))}: 记录五个APP的客服电话"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未记录客服电话"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开QQ"""
    rule4_xpath = ""
    evidence_steps = [
        "//*[contains(@package, 'weibo')] and //*[contains(@text, '客服') or contains(@text, '客户服务') or contains(@text, '电话')]",
        
        ]

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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开QQ"

    return False, "未打开QQ"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：发送电话号码列表到电脑"""
    rule5_xpaths = [
         "//*[contains(@text, '小红书') and contains(@text, '抖音') and contains(@text, '得物') and contains(@text, '汽水') and contains(@text, '微博') and not(contains(@text, '无')) ] and //*[contains(@package, 'mobileqq')] and //*[contains(@text, '我的电脑')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 发送电话号码列表到电脑"

    return False, "未发送信息"


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
        {"rule": "1. 打开多个APP查看客服电话", "score": 0.2, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 在APP中找到客服电话信息", "score": 0.4, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 记录五个APP的客服电话", "score": 0.6, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 打开QQ", "score": 0.8, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 发送电话号码列表到电脑", "score": 1.0, "satisfied": rule5_satisfied, "evidence": rule5_evidence}
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
        "BMK/first/3037778e",
        "BMK/second/6593885c",
        "BMK/third/5019bfe8",
        "BMK/fourth/0a48644c"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
