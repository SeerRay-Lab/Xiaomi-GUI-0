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


QUERY = "今晚我要在家里请 5 个朋友吃火锅。请打开盒马，帮我把一份海底捞牛油火锅底料、两份鲜切吊龙牛肉和一份火锅蔬菜拼盘加入购物车。去购物车查看这几样商品的总价，然后帮我算一下 AA 制的话每个人应该出多少钱发到qq里面我的电脑"
TASK_ID = 61
STEPRULES = """分段评分规则（5阶段）

1. 打开盒马 → 总分:0.2

2. 加入四种火锅商品到购物车 → 总分:0.4

3. 进入购物车查看总价 → 总分:0.6

4. 计算AA制每人应付金额 → 总分:0.8

5. 打开QQ并发送账单到电脑 → 总分:1.0

一票否决条件：
- 未打开盒马 → 分数:0
- 未加入购物车 → 分数:0
- 未打开QQ → 分数:0"""


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
    hippo_found = False
    cart_found = False
    qq_found = False

    for xml_string in xml_strings:
        if not hippo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'hippo')]", {})
                if match_flag == 1:
                    hippo_found = True
            except:
                pass

        if not cart_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '购物车') or contains(@text, '加入购物车') or contains(@ocr_texts, '购物车') or contains(@ocr_texts, '加入购物车')]", {})
                if match_flag == 1:
                    cart_found = True
            except:
                pass

        if not qq_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'mobileqq')]", {})
                if match_flag == 1:
                    qq_found = True
            except:
                pass

    if not hippo_found:
        return True, "未打开盒马"

    if not cart_found:
        return True, "未加入购物车"

    if not qq_found:
        return True, "未打开QQ"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开盒马"""
    rule1_xpath = "//*[contains(@package, 'hippo')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开盒马"

    return False, "未打开盒马"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：加入四种火锅商品到购物车"""
    rule2_xpaths = [
        "(//*[contains(@content-desc, '购物车')  and bbox_contains_point(../@bounds, $point)  and ../preceding-sibling::*[contains(@text, '海底捞') and contains(@text, '牛油')] ] ) or ( //*[contains(@text, '海底捞') and contains(@text, '牛油')] and //*[contains(@content-desc, '购物车')  and bbox_contains_point(../@bounds, $point)]  and //*[contains(@text, '收藏')] and //*[contains(@content-desc, '返回')])",
        "(//*[contains(@content-desc, '购物车')  and bbox_contains_point(../@bounds, $point)  and ../preceding-sibling::*[contains(@text, '吊龙')] ] ) or ( //*[contains(@text, '吊龙')] and //*[contains(@content-desc, '购物车')  and bbox_contains_point(../@bounds, $point)]  and //*[contains(@text, '收藏')] and //*[contains(@content-desc, '返回')])",
        "(//*[contains(@content-desc, '购物车')  and bbox_contains_point(../@bounds, $point)  and ../preceding-sibling::*[contains(@text, '蔬菜')] ] ) or ( //*[contains(@text, '蔬菜')] and //*[contains(@content-desc, '购物车')  and bbox_contains_point(../@bounds, $point)]  and //*[contains(@text, '收藏')] and //*[contains(@content-desc, '返回')])",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 加入火锅商品到购物车"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未加入购物车"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：进入购物车查看总价"""
    rule3_xpaths = [
        "//*[contains(@text, '购物车') or contains(@text, '总价') or contains(@text, '结算') or contains(@ocr_texts, '购物车') or contains(@ocr_texts, '总价')]",
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '价格') or contains(@ocr_texts, '¥') or contains(@ocr_texts, '元')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 进入购物车查看总价"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未查看购物车总价"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：计算AA制每人应付金额"""
    rule4_xpaths = [
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '除以') or contains(@text, '每人') or contains(@ocr_texts, '¥') or contains(@ocr_texts, '元')]",
        "//*[contains(@text, '6') or contains(@text, '除') or contains(@text, '分摊') or contains(@text, 'AA') or contains(@ocr_texts, '6') or contains(@ocr_texts, 'AA')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 计算AA制每人应付"

    return False, "未计算每人应付"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：打开QQ并发送账单到电脑"""
    rule5_xpaths = [
        "//*[contains(@package, 'mobileqq')] and //*[contains(@text, '我的电脑')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开QQ发送账单"

    return False, "未打开QQ发送账单"


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
        {"rule": "1. 打开盒马", "score": 0.2, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 加入四种火锅商品到购物车", "score": 0.4, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 进入购物车查看总价", "score": 0.6, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 计算AA制每人应付金额", "score": 0.8, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 打开QQ并发送账单到电脑", "score": 1.0, "satisfied": rule5_satisfied, "evidence": rule5_evidence}
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
        "BMK/first/67a30f9b",
        "BMK/second/54aa91f7",
        "BMK/third/698e07b5",
        "BMK/fourth/a3fc3d44"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
