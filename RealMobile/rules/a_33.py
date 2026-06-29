import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "分别去高德、携程上看看周六五道口全季酒店的价格，把相关权益信息总结给我，然后比较下去权益最好的平台订一个大床房。"
TASK_ID = 33
STEPRULES = """评分规则

1. 打开高德地图查看周六五道口全季酒店的价格和权益信息 → 总分:0.25

2. 打开携程查看周六五道口全季酒店的价格和权益信息 → 总分:0.5

3. 在权益最好的平台上预订一个大床房 → 总分:1.0

一票否决

1. 预订的不是大床房（预订了其他房型） → 总分:0

2. 在权益较差的平台预订而不是权益最好的平台 → 总分:0

3. 预订的不是周六或不是五道口全季酒店 → 总分:0"""


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
    # 一票否决：检查预订时的房间信息

    # 查找预订操作
    booking_xpaths = [
        "//*[contains(@text, '预订') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '立即预订')]"
    ]

    booking_found = False
    booking_idx = -1

    for i, xml_string in enumerate(xml_strings):
        for xpath in booking_xpaths:
            try:
                action_dict = actions[i] if i < len(actions) else {}
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    booking_found = True
                    booking_idx = i
                    break
            except:
                pass
        if booking_found:
            break

    # 如果找到了预订操作，检查是否预订的是正确的酒店、日期和房型
    if booking_found and booking_idx >= 0:
        xml_string = xml_strings[booking_idx]

        # 检查是否是五道口全季酒店
        hotel_found = False
        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '全季') or contains(@text, '五道口') or contains(@text, '全季酒店')]", {})
            if match_flag == 1:
                hotel_found = True
        except:
            pass

        if not hotel_found:
            return True, "预订的不是五道口全季酒店"

        # 检查是否是周六
        saturday_found = False
        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '周六') or contains(@text, '六') or contains(@text, 'Saturday')]", {})
            if match_flag == 1:
                saturday_found = True
        except:
            pass

        if not saturday_found:
            return True, "预订的不是周六"

        # 检查是否是大床房
        bed_type_found = False
        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '大床房') or contains(@text, '大床')]", {})
            if match_flag == 1:
                bed_type_found = True
        except:
            pass

        if not bed_type_found:
            return True, "预订的不是大床房"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：在高德地图查看周六五道口全季酒店的价格和权益"""
    rule1_xpaths = [
        "//*[contains(@package, 'amap') or contains(@text, '高德')]",
        "//*[contains(@text, '全季') or contains(@text, '五道口')]",
        "//*[contains(@text, '周六') or contains(@text, '六')]",
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '权益')]"
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在高德查看酒店信息"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未在高德查看酒店"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：在携程查看周六五道口全季酒店的价格和权益"""
    rule2_xpaths = [
        "//*[contains(@package, 'ctrip') or contains(@text, '携程')]",
        "//*[contains(@text, '全季') or contains(@text, '五道口')]",
        "//*[contains(@text, '周六') or contains(@text, '六')]",
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '权益') or contains(@text, '会员')]"
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在携程查看酒店信息"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未在携程查看酒店"



def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：在权益最好的平台预订大床房"""
    rule4_xpaths = [
        "//*[contains(@text, '订') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '大床房') or contains(@text, '大床')]",
        "//*[contains(@text, '全季') or contains(@text, '五道口')]",
        "//*[contains(@text, '确认') or contains(@text, '成功') or contains(@text, '订单')]"
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule4_xpaths)):
            xpath = rule4_xpaths[xpath_idx]
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 成功预订大床房"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未完成预订"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 33,
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

    # 先检查一票否决条件
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
            "rule": "1. 在高德查看酒店",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 在携程查看酒店",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 预订大床房",
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
    result = evaluate_trajectory(path="BMK/2026-04-29/高德地图_携程旅行/BMK评测/e41b93c5-2ab5-452c-9e18-bd3b1d0b7a2e")
    print(json.dumps(result, ensure_ascii=False, indent=2))
