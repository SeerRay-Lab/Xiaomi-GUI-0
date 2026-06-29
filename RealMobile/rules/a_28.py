import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "在淘宝搜索杯子，帮我挑一款纯钛材质、带折叠手柄的户外露营黑色水杯并加购物车"
TASK_ID = 28
STEPRULES = """评分规则

1. 打开淘宝App，搜索杯子相关产品 → 总分:0.25

2. 找到符合所有条件的水杯（纯钛材质、折叠手柄、户外露营、黑色） → 总分:0.5

3. 将符合条件的水杯加入购物车 → 总分:1.0

一票否决 
暂无"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
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

    return xml_strings, actions, steps


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    # 一票否决：检查加入购物车时的产品信息
    # 查找"加入购物车"或"已加入购物车"的确认页面
    add_to_cart_xpaths = [
        "//*[contains(@text, '加入购物车') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '已加入购物车')]"
    ]

    add_to_cart_found = False
    add_to_cart_idx = -1

    for i, xml_string in enumerate(xml_strings):
        for xpath in add_to_cart_xpaths:
            try:
                action_dict = actions[i] if i < len(actions) else {}
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    add_to_cart_found = True
                    add_to_cart_idx = i
                    break
            except:
                pass
        if add_to_cart_found:
            break

    # 如果找到了加入购物车的操作，检查产品是否符合所有要求
    if add_to_cart_found and add_to_cart_idx >= 0:
        xml_string = xml_strings[add_to_cart_idx]

        # 检查是否是杯子/水杯
        cup_found = False
        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '杯子') or contains(@text, '水杯') or contains(@text, '户外杯')]", {})
            if match_flag == 1:
                cup_found = True
        except:
            pass

        if not cup_found:
            return True, "加入购物车的不是杯子产品"

        # 检查是否包含所有必要属性
        titanium_found = False
        foldable_handle_found = False
        black_found = False

        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '纯钛') or contains(@text, '钛')]", {})
            if match_flag == 1:
                titanium_found = True
        except:
            pass

        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '折叠手柄') or contains(@text, '折叠')]", {})
            if match_flag == 1:
                foldable_handle_found = True
        except:
            pass

        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '黑色') or contains(@text, '黑')]", {})
            if match_flag == 1:
                black_found = True
        except:
            pass

        # 如果缺少任何一项属性，则判定为错误选择
        if not (titanium_found and foldable_handle_found and black_found):
            missing = []
            if not titanium_found:
                missing.append("纯钛材质")
            if not foldable_handle_found:
                missing.append("折叠手柄")
            if not black_found:
                missing.append("黑色")
            return True, f"加入购物车的杯子缺少以下属性: {','.join(missing)}"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开淘宝，搜索杯子"""
    rule1_xpaths = [
        "//*[contains(@package, 'taobao') or contains(@text, '淘宝')]",
        "//*[contains(@text, '搜索') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '杯子') or contains(@text, '水杯')]",
        "//*[contains(@text, '户外') or contains(@text, '露营') or contains(@text, '旅游')]"
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

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索杯子"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未搜索杯子"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：找到符合所有条件的水杯"""
    rule2_xpaths = [
        "//*[contains(@text, '纯钛') or contains(@text, '钛')]",
        "//*[contains(@text, '折叠手柄') or contains(@text, '折叠') or contains(@text, '手柄')]",
        "//*[contains(@text, '黑色') or contains(@text, '黑')]",
        "//*[contains(@text, '户外') or contains(@text, '露营') or contains(@text, '杯子')]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule2_xpaths)):
            xpath = rule2_xpaths[xpath_idx]
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

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 找到符合条件的水杯"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未找到符合条件的水杯"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：将水杯加入购物车"""
    rule3_xpaths = [
        "//*[contains(@text, '加入购物车') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '已加入购物车') or contains(@text, '购物车')]",
        "//*[contains(@text, '纯钛') or contains(@text, '钛')]",
        "//*[contains(@text, '黑') or contains(@text, '折叠')]"
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule3_xpaths)):
            xpath = rule3_xpaths[xpath_idx]
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

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 成功加入购物车"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未加入购物车"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 28,
            "path": "...",
            "steprules": "...",
            "total_score": 1.0,
            "details": [...]
        }
    """
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
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.25
    if rule2_satisfied:
        max_score = 0.5
    if rule3_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 搜索杯子",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 找到符合条件的水杯",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 加入购物车",
            "score": 1.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        }
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
    result = evaluate_trajectory(path="BMK/2026-04-29/淘宝/BMK评测/e41582f0-5429-4245-9792-990aa9ad7e6e")
    print(json.dumps(result, ensure_ascii=False, indent=2))
