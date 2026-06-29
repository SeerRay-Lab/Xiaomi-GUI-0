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


QUERY = "我明天就要临时领养一只 2 个月大的小橘猫了，我现在完全是个新手，手忙脚乱的。请你先去小红书站搜一下新手养猫必备物品清单，总结出最核心的 5 样东西。然后去抖音商城，结合小红书上大家的避雷评价，帮我把这 5 样东西挑选性价比高的品牌加入购物车。最后去今日头条发个微头条，把我挑选的这些东西也分享给大家"
TASK_ID = 98
STEPRULES = """分段评分规则（6阶段）

1. 打开小红书搜索养猫清单 → 总分:0.167

2. 查看并总结5样物品 → 总分:0.333

3. 打开抖音商城搜索物品 → 总分:0.5

4. 挑选性价比高的品牌 → 总分:0.667

5. 加入购物车 → 总分:0.833

6. 打开今日头条发微头条 → 总分:1.0

一票否决条件：
- 未打开小红书 → 分数:0
- 未打开抖音 → 分数:0
- 未打开今日头条 → 分数:0"""


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
    aweme_found = False
    news_found = False

    for xml_string in xml_strings:
        if not xhs_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs')]", {})
                if match_flag == 1:
                    xhs_found = True
            except:
                pass

        if not aweme_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'aweme')]", {})
                if match_flag == 1:
                    aweme_found = True
            except:
                pass

        if not news_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'article.news')]", {})
                if match_flag == 1:
                    news_found = True
            except:
                pass

    if not xhs_found:
        return True, "未打开小红书"

    if not aweme_found:
        return True, "未打开抖音"

    if not news_found:
        return True, "未打开今日头条"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书搜索养猫清单"""
    rule1_xpaths = [
        "//*[contains(@package, 'xhs')]",
        "//*[contains(@text, '养猫') or contains(@text, '必备') or contains(@text, '清单') or contains(@text, '搜索') or contains(@ocr_texts, '养猫') or contains(@ocr_texts, '必备')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书搜索"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未搜索养猫清单"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：查看并总结5样物品"""
    rule2_xpaths = [
        "//*[contains(@text, '清单') or contains(@text, '物品') or contains(@text, '必备') or contains(@text, '推荐') or contains(@ocr_texts, '清单') or contains(@ocr_texts, '物品')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 查看清单"

    return False, "未查看清单"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开抖音商城搜索物品"""
    rule3_xpaths = [
        "//*[contains(@package, 'aweme')]",
        "//*[contains(@text, '商城') or contains(@text, '养猫') or contains(@text, '物品') or contains(@text, '搜索') or contains(@ocr_texts, '商城') or contains(@ocr_texts, '物品')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开抖音搜索"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未打开抖音商城"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：挑选性价比高的品牌"""
    rule4_xpaths = [
        "//*[contains(@text, '性价比') or contains(@text, '品牌') or contains(@text, '价格') or contains(@text, '评价') or contains(@ocr_texts, '性价比') or contains(@ocr_texts, '品牌')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 挑选品牌"

    return False, "未挑选品牌"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：加入购物车"""
    rule5_xpaths = [
        "//*[contains(@content-desc, '加入购物车') or contains(@text, '加入购物车') or contains(@text, '加购') or contains(@ocr_texts, '加入购物车')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 加入购物车"

    return False, "未加入购物车"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：打开今日头条发微头条"""
    rule6_xpaths = [
        "//*[contains(@package, 'article.news')]",
        "//*[contains(@text, '微头条') or contains(@text, '发布') or contains(@text, '分享') or contains(@ocr_texts, '微头条') or contains(@ocr_texts, '发布')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开今日头条发微头条"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule6_xpaths)}"

    return False, "未发微头条"


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
        {"rule": "1. 打开小红书搜索养猫清单", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 查看并总结5样物品", "score": 0.333, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 打开抖音商城搜索物品", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 挑选性价比高的品牌", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 加入购物车", "score": 0.833, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 打开今日头条发微头条", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/fdf70b73",
        "BMK/second/43c72e74",
        "BMK/third/229f2d01",
        "BMK/fourth/04951d94"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
