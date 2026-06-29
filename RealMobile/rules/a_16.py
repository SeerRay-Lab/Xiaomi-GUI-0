import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "去微博热搜榜看看今天有没有关于外星人降临的热搜，如果有，把具体内容私信发给雷军的抖音号"
TASK_ID = 16
STEPRULES = """评分规则

去微博热搜榜查看当日榜单并搜索"外星人降临"相关条目 → 总分:0.25

正确判断是否存在相关热搜（基于标题与内容语义匹配） → 总分:0.5

3.1 存在：整理该热搜的具体内容（标题、要点、来源链接）并私信发送给已认证的"雷军"抖音号 → 总分:1.0

3.2 不存在：明确说明未找到相关热搜且不进行私信发送 → 总分:1.0

一票否决

暂无"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
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

    return xml_strings, actions


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开微博热搜榜"""
    rule1_xpaths = [
        "//*[contains(@package, 'weibo') or contains(@text, '微博')]",
        "//*[contains(@text, '热搜') or contains(@text, '热搜榜')]",
        "//*[contains(@text, '外星人') or contains(@text, '降临')]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule1_xpaths)):
            xpath = rule1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    continue
            except:
                pass

        if sum(checked) >= 2:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 进入微博热搜榜"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未进入微博热搜榜"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str, bool]:
    """规则2：判断是否存在相关热搜，返回(是否满足规则2, 证据, 是否存在热搜)"""

    exist_xpaths = [
        "//*[contains(@text, '外星人') and (contains(@text, '降临') or contains(@text, '事件'))]",
        "//*[contains(@text, 'UFO') or contains(@text, '不明飞行物')]"
    ]

    exist_found = False
    not_exist_found = False
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath in exist_xpaths:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    exist_found = True
                    evidence_steps.append(i)
                    break
            except:
                pass


    if exist_found:
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 发现外星人降临相关热搜", True
    else:
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 确认暂无相关热搜", False


def evaluate_rule_3_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3.1：存在热搜，整理内容并私信发送给雷军抖音号"""
    rule3_1_xpaths = [
        "//*[contains(@package, 'douyin') or contains(@text, '抖音')]",
        "//*[contains(@text, '雷军')]",
        "//*[contains(@text, '私信') or contains(@text, '消息')]",
        "//*[contains(@text, '发送') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '外星人') or contains(@text, '热搜')]"
    ]

    checked = [False] * len(rule3_1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule3_1_xpaths)):
            xpath = rule3_1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    continue
            except:
                pass

        if sum(checked) >= 4:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 成功私信雷军抖音号"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_1_xpaths)}"

    return False, "未完成私信发送"


def evaluate_rule_3_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3.2：不存在热搜，明确说明未找到且不进行私信"""
    rule3_2_xpaths = [
        "//*[contains(@text, '未找到') and (contains(@text, '热搜') or contains(@text, '外星人'))]",
        "//*[contains(@text, '没有') and (contains(@text, '外星人') or contains(@text, '相关热搜'))]"
    ]

    found_count = 0
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath in rule3_2_xpaths:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    found_count += 1
                    evidence_steps.append(i)
                    break
            except:
                pass

    if found_count >= 1:
        douyin_xpaths = ["//*[contains(@package, 'douyin') or contains(@text, '抖音')]"]
        douyin_found = False
        for xml_string in xml_strings:
            for xpath in douyin_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                    if match_flag == 1:
                        douyin_found = True
                        break
                except:
                    pass

        if not douyin_found:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 明确说明未找到热搜，未进行私信"
        else:
            return False, "检测到抖音操作，不符合规则3.2"

    return False, "未明确说明未找到热搜"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 16,
            "path": "...",
            "steprules": "...",
            "total_score": 1.0,
            "details": [...]
        }
    """
    try:
        xml_strings, actions = load_trajectory_data(path)
    except Exception as e:
        print(f"Error loading trajectory data: {e}")
        return {
            "query": QUERY,
            "id": TASK_ID,
            "path": path,
            "steprules": STEPRULES,
            "total_score": 0.0,
            "details": [],
            "rejection_reason": "无法加载轨迹数据"
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

    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence, hot_search_exists = evaluate_rule_2(xml_strings, actions)
    rule3_1_satisfied, rule3_1_evidence = evaluate_rule_3_1(xml_strings, actions)
    rule3_2_satisfied, rule3_2_evidence = evaluate_rule_3_2(xml_strings, actions)

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_1_satisfied = False
        rule3_2_satisfied = False
    elif not rule2_satisfied:
        rule3_1_satisfied = False
        rule3_2_satisfied = False
    else:
        if hot_search_exists:
            rule3_2_satisfied = False
        else:
            rule3_1_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.25
    if rule2_satisfied:
        max_score = 0.5
    if rule3_1_satisfied or rule3_2_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 查看热搜榜",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 判断是否存在",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        }
    ]

    if rule2_satisfied:
        if hot_search_exists:
            details.append({
                "rule": "3.1 私信雷军抖音号",
                "score": 1.0,
                "satisfied": rule3_1_satisfied,
                "evidence": rule3_1_evidence
            })
        else:
            details.append({
                "rule": "3.2 说明未找到",
                "score": 1.0,
                "satisfied": rule3_2_satisfied,
                "evidence": rule3_2_evidence
            })
    else:
        details.append({
            "rule": "3.1 私信雷军抖音号",
            "score": 1.0,
            "satisfied": False,
            "evidence": "规则2未满足"
        })

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
    result = evaluate_trajectory(path="BMK/2026-04-29/微博_抖音/BMK评测/132130a6-6990-4182-923b-924dbc8b5d20")
    print(json.dumps(result, ensure_ascii=False, indent=2))
