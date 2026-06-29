import json
import os
import sys
from typing import Dict, List, Any, Tuple

# 导入已有的工具函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "对比一下得物、抖音商城以及橘子app上苹果17的价格，最后总结一下三个平台的价格对比"
TASK_ID = 6
STEPRULES = """1. 在得物中查看苹果17的价格信息 → 总分:0.33

2. 在抖音商城中查看苹果17的价格信息 → 总分:0.66

3. 在橘子app中查看苹果17的价格信息 → 总分:1.0"""


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


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：在得物中查看苹果17的价格信息"""
    rule1_xpaths = [
        "//*[contains(@package, 'duapp') ] and //*[contains(@text, '苹果17') or contains(@ocr_texts, '苹果17') or contains(@text, 'iPhone 17') or contains(@ocr_texts, 'iPhone 17') or contains(@text, '苹果') or contains(@ocr_texts, '苹果')]",
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule1_xpaths) - 1, -1, -1):
            xpath = rule1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    break
            except:
                pass

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在得物中查看了苹果17的价格"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未在得物中查看苹果17价格"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：在抖音商城中查看苹果17的价格信息"""
    rule2_xpaths = [
        "//*[contains(@package, 'ugc.aweme') ] and //*[contains(@text, '苹果17') or contains(@ocr_texts, '苹果17') or contains(@text, 'iPhone 17') or contains(@ocr_texts, 'iPhone 17') or contains(@text, '苹果') or contains(@ocr_texts, '苹果')]",
        ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule2_xpaths) - 1, -1, -1):
            xpath = rule2_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    break
            except:
                pass

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在抖音商城中查看了苹果17的价格"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未在抖音商城中查看苹果17价格"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：在橘子app中查看苹果17的价格信息"""
    rule3_xpaths = [
        "//*[contains(@package, 'zhuoqinglidashi')]",
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]


        for xpath_idx in range(len(rule3_xpaths) - 1, -1, -1):
            xpath = rule3_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    break
            except:
                pass

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在橘子app中查看了苹果17的价格"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未在橘子app中查看苹果17价格"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "对比一下得物、抖音商城以及橘子app上苹果17的价格...",
            "id": 6,
            "path": "BMK/...",
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

    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)

    details = [
        {
            "rule": "在得物中查看苹果17的价格信息",
            "score": 0.33 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "在抖音商城中查看苹果17的价格信息",
            "score": 0.33 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "在橘子app中查看苹果17的价格信息",
            "score": 0.34 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        }
    ]

    # 最终总分 = 所有满足的规则的分值之和
    total_score = 0.0
    for detail in details:
        if detail['satisfied']:
            total_score += detail['score']

    return {
        "query": QUERY,
        "id": TASK_ID,
        "path": path,
        "steprules": STEPRULES,
        "total_score": total_score,
        "details": details,
        "rejection_reason": None
    }


if __name__ == "__main__":
    paths = [
        "BMK/first/0017f74e",
        "BMK/second/c83cc543",
        "BMK/third/d94d80c2",
        "BMK/fourth/6b8db936"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
