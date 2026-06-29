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


QUERY = "打开腾讯视频看一下士兵突击的主演是谁，去微博上关注一下他，然后今日头条帮我看一下这人有没有唱过什么歌，再去汽水音乐播放一下他唱的任意一首歌，最后帮我在得物上找一下关于他的周边"
TASK_ID = 59
STEPRULES = """分段评分规则（6阶段）

1. 打开腾讯视频并查看士兵突击主演 → 总分:0.167

2. 打开微博并关注该演员 → 总分:0.333

3. 打开今日头条查看演员的歌曲信息 → 总分:0.5

4. 打开汽水音乐并播放演员的歌 → 总分:0.667

5. 打开得物 → 总分:0.833

6. 搜索演员周边 → 总分:1.0

一票否决条件：
- 未打开腾讯视频 → 分数:0
- 未查看士兵突击 → 分数:0
- 未打开微博 → 分数:0
- 未打开汽水音乐 → 分数:0
- 未打开得物 → 分数:0"""


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
    qqlive_found = False
    soldier_found = False
    weibo_found = False
    soda_found = False
    duapp_found = False

    for xml_string in xml_strings:
        if not qqlive_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'qqlive')]", {})
                if match_flag == 1:
                    qqlive_found = True
            except:
                pass

        if not soldier_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '士兵突击') or contains(@ocr_texts, '士兵突击')]", {})
                if match_flag == 1:
                    soldier_found = True
            except:
                pass

        if not weibo_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'weibo')]", {})
                if match_flag == 1:
                    weibo_found = True
            except:
                pass

        if not soda_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'luna.music')]", {})
                if match_flag == 1:
                    soda_found = True
            except:
                pass

        if not duapp_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'duapp')]", {})
                if match_flag == 1:
                    duapp_found = True
            except:
                pass

    if not qqlive_found:
        return True, "未打开腾讯视频"

    if not soldier_found:
        return True, "未查看士兵突击"

    if not weibo_found:
        return True, "未打开微博"

    if not soda_found:
        return True, "未打开汽水音乐"

    if not duapp_found:
        return True, "未打开得物"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开腾讯视频并查看士兵突击主演"""
    rule1_xpaths = [
        "//*[contains(@package, 'qqlive')]",
        "//*[contains(@text, '士兵突击') or contains(@text, '主演') or contains(@text, '演员') or contains(@ocr_texts, '士兵突击') or contains(@ocr_texts, '主演')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开腾讯视频查看主演"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未查看士兵突击主演"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开微博并关注该演员"""
    rule2_xpaths = [
        "//*[contains(@package, 'weibo')]",
        "//*[contains(@text, '关注') or contains(@text, '粉丝') or contains(@text, '主页') or contains(@ocr_texts, '关注') or contains(@ocr_texts, '粉丝')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开微博关注演员"

    return False, "未在微博关注演员"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开今日头条查看演员的歌曲信息"""
    rule3_xpaths = [
        "//*[contains(@package, 'article.news')]",
        "//*[contains(@text, '歌曲') or contains(@text, '唱歌') or contains(@text, '音乐') or contains(@text, '演员') or contains(@ocr_texts, '歌曲') or contains(@ocr_texts, '唱歌')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开今日头条查看歌曲"

    return False, "未查看演员歌曲"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开汽水音乐并播放演员的歌"""
    rule4_xpaths = [
        "//*[contains(@package, 'luna.music')]",
        "//*[contains(@text, '播放') or contains(@text, '音乐') or contains(@text, '歌曲') or contains(@ocr_texts, '播放') or contains(@ocr_texts, '音乐')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开汽水音乐播放歌曲"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未在汽水音乐播放"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：打开得物"""
    rule5_xpath = "//*[contains(@package, 'duapp')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开得物"

    return False, "未打开得物"


def evaluate_rule_6(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则6：搜索演员周边"""
    rule6_xpaths = [
        "//*[contains(@text, '周边') or contains(@text, '周边商品') or contains(@text, '搜索') or contains(@ocr_texts, '周边') or contains(@ocr_texts, '周边商品')]",
        "//*[contains(@text, '周边') or contains(@text, '衣服') or contains(@text, '帽子') or contains(@text, '商品') or contains(@ocr_texts, '周边') or contains(@ocr_texts, '商品')]",
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
        return True, f"步骤{sorted(set(evidence_steps))}: 搜索演员周边"

    return False, "未搜索演员周边"


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
        {"rule": "1. 打开腾讯视频并查看士兵突击主演", "score": 0.167, "satisfied": rule1_satisfied, "evidence": rule1_evidence},
        {"rule": "2. 打开微博并关注该演员", "score": 0.333, "satisfied": rule2_satisfied, "evidence": rule2_evidence},
        {"rule": "3. 打开今日头条查看演员的歌曲信息", "score": 0.5, "satisfied": rule3_satisfied, "evidence": rule3_evidence},
        {"rule": "4. 打开汽水音乐并播放演员的歌", "score": 0.667, "satisfied": rule4_satisfied, "evidence": rule4_evidence},
        {"rule": "5. 打开得物", "score": 0.833, "satisfied": rule5_satisfied, "evidence": rule5_evidence},
        {"rule": "6. 搜索演员周边", "score": 1.0, "satisfied": rule6_satisfied, "evidence": rule6_evidence}
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
        "BMK/first/61898858",
        "BMK/second/b2963b37",
        "BMK/third/6719fcf9",
        "BMK/fourth/8f03aae8"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
