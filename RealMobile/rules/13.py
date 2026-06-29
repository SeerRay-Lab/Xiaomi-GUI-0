import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple

# 导入已有的工具函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "我有3个小时的空闲，帮我算一下我最多能看b站热门视频前几个"
TASK_ID = 13
STEPRULES = """评分规则（分阶段验证进度，只验证不计算）

1. 打开B站App → 总分:0.5

2. 点击热门按钮 → 总分:1.0

一票否决条件：
- 未打开B站App → 分数:0
- 未点击热门按钮 → 分数:0
"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """加载轨迹数据，优先使用 _ocr.xml"""
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
            # 如果 _ocr.xml 不存在，使用原始文件
            xml_path = os.path.join(path, step['xml'])

        if not os.path.exists(xml_path):
            continue

        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_strings.append(f.read())

        # 构造 action_dict 格式
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


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    # 一票否决条件1: 未打开B站App
    has_bilibili = False
    # 一票否决条件2: 未点击热门按钮
    has_hot_button = False

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否打开了B站(package包含'bili')
            for elem in root.iter():
                package = elem.get('package', '')
                if 'bili' in package:
                    has_bilibili = True

            # 检查是否点击了热门按钮(包含'热门'、'榜单'或'排行'关键词)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                if ('热门' in combined or '榜单' in combined or '排行' in combined):
                    has_hot_button = True
        except Exception as e:
            pass

    # 检查否决条件
    if not has_bilibili:
        return True, "未打开B站App"

    if not has_hot_button:
        return True, "未点击热门按钮"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开B站App"""
    rule1_xpaths = [
        "//*[contains(@package, 'bili')]"
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
            except Exception as e:
                pass

    # 需要打开B站App
    if checked[0]:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开B站App"

    return False, "未打开B站App"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：点击热门按钮"""
    rule2_xpaths = [
        "//*[(contains(@text, '热门') or contains(@ocr_texts, '热门')) and bbox_contains_point(../@bounds, $point)]"
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
            except Exception as e:
                pass

    # 至少需要匹配一个关键词表示点击了热门按钮
    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 点击热门按钮"

    return False, "未点击热门按钮"




def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 13,
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

    # 先检查一票否决条件
    is_rejected, rejection_reason = check_veto_conditions(xml_strings, actions)
    if is_rejected:
        return {
            "query": QUERY,
            "id": TASK_ID,
            "path": path,
            "steprules": STEPRULES,
            "total_score": 0.0,
            "details": [],
            "rejection_reason": rejection_reason
        }

    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)

    details = [
        {
            "rule": "打开B站App",
            "score": 0.5 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "点击热门按钮",
            "score": 1.0 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        }
    ]

    # 最终总分 = 最高满足的规则分值
    max_score = 0.0
    for detail in details:
        if detail['satisfied']:
            max_score = max(max_score, detail['score'])

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
    paths = [
        "BMK/first/070126e0",
        "BMK/second/95bb7174",
        "BMK/third/0fbf463e",
        "BMK/fourth/6e447613"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
