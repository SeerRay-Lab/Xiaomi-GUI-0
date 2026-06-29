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


QUERY = "下周就是我的结婚纪念日，我有 1000 块钱预算。要求使用小红书查找礼物、烛光晚餐以及合适的氛围音乐，然后使用得物购买礼物、并且把烛光晚餐需要的食材加入盒马购物车，最终在汽水音乐收藏这些音乐"
TASK_ID = 36
STEPRULES = """分段评分规则（6阶段）

1. 打开小红书 → 总分:0.167

2. 在小红书查找礼物、烛光晚餐、氛围音乐 → 总分:0.334

3. 打开得物购买礼物 → 总分:0.5

4. 打开盒马添加食材到购物车 → 总分:0.667

5. 打开汽水音乐 → 总分:0.834

6. 搜索并找到氛围音乐 → 总分:1.0

一票否决条件：
- 未打开小红书 → 分数:0
- 未找到礼物、烛光晚餐或音乐 → 分数:0"""


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
    gift_found = False
    dinner_found = False
    music_found = False

    for xml_string in xml_strings:
        if not xhs_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs')]", {})
                if match_flag == 1:
                    xhs_found = True
            except:
                pass

        if not gift_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '礼物') or contains(@text, '礼品') or contains(@ocr_texts, '礼物')]", {})
                if match_flag == 1:
                    gift_found = True
            except:
                pass

        if not dinner_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '烛光晚餐') or contains(@text, '晚餐') or contains(@ocr_texts, '烛光晚餐')]", {})
                if match_flag == 1:
                    dinner_found = True
            except:
                pass

        if not music_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '音乐') or contains(@text, '氛围') or contains(@ocr_texts, '音乐') or contains(@ocr_texts, '氛围')]", {})
                if match_flag == 1:
                    music_found = True
            except:
                pass

    if not xhs_found:
        return True, "未打开小红书"

    if not (gift_found and dinner_found and music_found):
        reason = "未找到"
        if not gift_found:
            reason += "礼物、"
        if not dinner_found:
            reason += "烛光晚餐、"
        if not music_found:
            reason += "音乐、"
        return True, reason.rstrip("、")

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
    """规则2：在小红书查找礼物、烛光晚餐、氛围音乐"""
    rule2_xpaths = [
        "//*[contains(@text, '礼物') or contains(@text, '礼品') or contains(@ocr_texts, '礼物')]",
        "//*[contains(@text, '烛光晚餐') or contains(@text, '晚餐') or contains(@ocr_texts, '烛光晚餐')]",
        "//*[contains(@text, '音乐') or contains(@text, '氛围') or contains(@ocr_texts, '音乐')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查找礼物、烛光晚餐、氛围音乐"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未查找到相关内容"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开得物购买礼物"""
    rule3_xpaths = [
        "//*[contains(@package, 'duapp') or contains(@text, '得物')]",
        "//*[contains(@text, '购买') or contains(@text, '加入购物车') or contains(@ocr_texts, '购买')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 在得物购买礼物"

    return False, "未在得物购买礼物"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开盒马添加食材到购物车"""
    rule4_xpaths = [
        "//*[contains(@package, 'hippo') or contains(@text, '盒马')]",
        "//*[contains(@text, '加入购物车') or contains(@text, '加购') or contains(@ocr_texts, '加入购物车')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 在盒马添加食材到购物车"

    return False, "未在盒马添加食材"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：打开汽水音乐"""
    rule5_xpath = "//*[contains(@package, 'luna.music')]"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule5_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开汽水音乐"

    return False, "未打开汽水音乐"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：搜索并找到氛围音乐"""
    # 先从小红书页提取出现过的音乐关键词
    xhs_music_keywords = set()
    for i, xml_string in enumerate(xml_strings):
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                package = elem.get('package', '')
                if 'xhs' in package:
                    text = elem.get('text', '')
                    ocr_texts = elem.get('ocr_texts', '')
                    if text and ('音乐' in text or '背景' in text or '氛围' in text):
                        xhs_music_keywords.add(text)
                    if ocr_texts and ('音乐' in ocr_texts or '背景' in ocr_texts or '氛围' in ocr_texts):
                        xhs_music_keywords.add(ocr_texts)
        except:
            pass

    # 查找luna.music中出现过的小红书音乐关键词
    evidence_steps = []
    for i, xml_string in enumerate(xml_strings):
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                package = elem.get('package', '')
                text = elem.get('text', '')

                if package and 'luna.music' in package and text:
                    for keyword in xhs_music_keywords:
                        if keyword in text or text in keyword:
                            evidence_steps.append(i)
                            return True, f"步骤{sorted(set(evidence_steps))}: 搜索并找到氛围音乐"
        except:
            pass

    return False, "未在汽水音乐找到相关音乐"


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
        {"rule": "2. 查找礼物、烛光晚餐、氛围音乐", "score": 0.334, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 在得物购买礼物", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 在盒马添加食材到购物车", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 打开汽水音乐", "score": 0.834, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 搜索并找到氛围音乐", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/1af3f177",
        "BMK/second/58664f2c",
        "BMK/third/20b5730a",
        "BMK/fourth/7fe1972e"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
