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


QUERY = "分别给抖音、微博、b站、小红书上雷军最新发布的内容点赞"
TASK_ID = 28
STEPRULES = """分段评分规则（4阶段）

1. 打开抖音并给雷军最新内容点赞 → 总分:0.25

2. 打开微博并给雷军最新内容点赞 → 总分:0.5

3. 打开b站并给雷军最新内容点赞 → 总分:0.75

4. 打开小红书并给雷军最新内容点赞 → 总分:1.0

一票否决条件：
- 未打开相应平台 → 分数:0
- 未找到雷军内容 → 分数:0"""


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
    douyin_found = False
    weibo_found = False
    bili_found = False
    xhs_found = False
    leijun_found = False

    for xml_string in xml_strings:
        text_content = extract_text_content(xml_string)

        if not douyin_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'aweme') or contains(@package, 'douyin')]", {})
                if match_flag == 1:
                    douyin_found = True
            except:
                pass

        if not weibo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'weibo')]", {})
                if match_flag == 1:
                    weibo_found = True
            except:
                pass

        if not bili_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'bili')]", {})
                if match_flag == 1:
                    bili_found = True
            except:
                pass

        if not xhs_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs')]", {})
                if match_flag == 1:
                    xhs_found = True
            except:
                pass

        if not leijun_found and '雷军' in text_content:
            leijun_found = True

    if not douyin_found or not weibo_found or not bili_found or not xhs_found:
        reason = "未打开相应平台"
        if not douyin_found:
            reason += "（未打开抖音）"
        if not weibo_found:
            reason += "（未打开微博）"
        if not bili_found:
            reason += "（未打开b站）"
        if not xhs_found:
            reason += "（未打开小红书）"
        return True, reason

    if not leijun_found:
        return True, "未找到雷军内容"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音并给雷军最新内容点赞"""
    rule1_xpaths = [
        "//*[contains(@package, 'aweme') or contains(@package, 'douyin')] and //*[contains(@text, '雷军') or contains(@ocr_texts, '雷军')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开抖音并给雷军最新内容点赞"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未完成抖音点赞"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开微博并给雷军最新内容点赞"""
    rule2_xpaths = [
        "//*[contains(@package, 'weibo')] and //*[contains(@text, '雷军') or contains(@ocr_texts, '雷军')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开微博并给雷军最新内容点赞"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未完成微博点赞"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开b站并给雷军最新内容点赞"""
    rule3_xpaths = [
        "//*[contains(@package, 'bili')] and //*[contains(@text, '雷军') or contains(@ocr_texts, '雷军')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开b站并给雷军最新内容点赞"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未完成b站点赞"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开小红书并给雷军最新内容点赞"""
    rule4_xpaths = [
        "//*[contains(@package, 'xhs')] and //*[contains(@text, '雷军') or contains(@ocr_texts, '雷军')]",
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

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书并给雷军最新内容点赞"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未完成小红书点赞"


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

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule3_satisfied:
        rule4_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.25
    if rule2_satisfied:
        max_score = 0.5
    if rule3_satisfied:
        max_score = 0.75
    if rule4_satisfied:
        max_score = 1.0

    details = [
        {"rule": "1. 打开抖音并给雷军最新内容点赞", "score": 0.25, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 打开微博并给雷军最新内容点赞", "score": 0.5, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 打开b站并给雷军最新内容点赞", "score": 0.75, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 打开小红书并给雷军最新内容点赞", "score": 1.0, "satisfied": rule4_satisfied, "evidence": rule4_evidence}
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
        "BMK/first/11b44754",
        "BMK/second/03a39f5e",
        "BMK/third/aa783c70",
        "BMK/fourth/869131fb"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
