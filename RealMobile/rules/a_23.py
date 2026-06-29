import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "帮我买一张明天早上8点前从上海飞往北京的国航头等舱机票，如果没有头等舱，就帮我查一下明天的高铁时刻表"
TASK_ID = 23
STEPRULES = """评分规则

1. 打开携程旅行App，搜索明天上海飞北京、早上8点前的国航航班 → 总分:0.25

2. 确认查看到国航航班的头等舱信息 → 总分:0.5

3.1 头等舱可预订：完成头等舱机票的下单与支付 → 总分:1.0

3.2 头等舱无法预订：查看明天高铁时刻表并浏览高铁班次信息 → 总分:1.0

一票否决

1. 购买了错误日期、错误出发地、错误目的地或错误航空公司的机票 → 总分:0

2. 在头等舱有货的情况下，没有完成购票流程直接查看高铁 → 总分:0"""


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
    # 一票否决1：购买错误的日期、出发地、目的地或航空公司
    # 检查支付/购票成功的页面中是否包含错误信息
    booking_fail_xpaths = [
        "//*[contains(@text, '支付') and contains(@text, '成功')]",
        "//*[contains(@text, '订单') and contains(@text, '确认')]",
        "//*[contains(@text, '购票') and contains(@text, '成功')]"
    ]

    payment_found_idx = -1
    for i, xml_string in enumerate(xml_strings):
        for xpath in booking_fail_xpaths:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                if match_flag == 1:
                    payment_found_idx = i
                    break
            except:
                pass
        if payment_found_idx >= 0:
            break

    # 如果找到支付页面，检查是否包含错误的目的地/出发地/航空公司
    if payment_found_idx >= 0:
        xml_string = xml_strings[payment_found_idx]

        # 检查是否包含上海和北京
        shanghai_found = False
        beijing_found = False
        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '上海') or contains(@text, '浦东') or contains(@text, '虹桥')]", {})
            if match_flag == 1:
                shanghai_found = True
        except:
            pass

        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '北京') or contains(@text, '首都') or contains(@text, '大兴')]", {})
            if match_flag == 1:
                beijing_found = True
        except:
            pass

        # 检查是否包含国航
        caac_found = False
        try:
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '国航') or contains(@text, 'CA')]", {})
            if match_flag == 1:
                caac_found = True
        except:
            pass

        # 如果购票但缺少必要信息，则判定为错误购票
        if not (shanghai_found and beijing_found and caac_found):
            return True, "检测到购买了错误的航班"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开携程，搜索明天上海飞北京、早上8点前的国航航班"""
    rule1_xpaths = [
        "//*[contains(@package, 'ctrip') or contains(@text, '携程')]",
        "//*[contains(@text, '上海') or contains(@text, '浦东') or contains(@text, '虹桥')]",
        "//*[contains(@text, '北京') or contains(@text, '首都') or contains(@text, '大兴')]",
        "//*[contains(@text, '明天') or contains(@text, '早上') or contains(@text, '8')]",
        "//*[contains(@text, '国航') or contains(@text, 'CA')]"
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

        if sum(checked) >= 4:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索国航航班"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未搜索航班信息"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：确认查看到国航航班的头等舱信息"""
    rule2_xpaths = [
        "//*[contains(@text, '国航') or contains(@text, 'CA')]",
        "//*[contains(@text, '头等舱') or contains(@text, '头等')]",
        "//*[contains(@text, '¥') or contains(@text, '元') or contains(@text, '价格')]",
        "//*[contains(@text, '时间') or contains(@text, '出发')]"
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 确认头等舱信息"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未确认头等舱信息"


def evaluate_rule_3_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3.1：头等舱可预订，完成购票与支付"""
    rule3_1_xpaths = [
        "//*[contains(@text, '预订') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '支付') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '确认') and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '成功') or contains(@text, '已完成')]"
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

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 完成购票与支付"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_1_xpaths)}"

    return False, "未完成购票与支付"


def evaluate_rule_3_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3.2：头等舱无法预订，查看明天高铁时刻表"""
    rule3_2_xpaths = [
        "//*[contains(@text, '无货') or contains(@text, '已满') or contains(@text, '售罄') or contains(@text, '无法')]",
        "//*[contains(@text, '高铁') or contains(@text, '动车') or contains(@text, 'G') or contains(@text, 'D')]",
        "//*[contains(@text, '明天') or contains(@text, '时刻') or contains(@text, '班次')]",
        "//*[contains(@text, '上海') or contains(@text, '北京')]"
    ]

    checked = [False] * len(rule3_2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule3_2_xpaths)):
            xpath = rule3_2_xpaths[xpath_idx]
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 查看高铁时刻表"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_2_xpaths)}"

    return False, "未查看高铁时刻表"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 23,
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
    rule3_1_satisfied, rule3_1_evidence = evaluate_rule_3_1(xml_strings, actions)
    rule3_2_satisfied, rule3_2_evidence = evaluate_rule_3_2(xml_strings, actions)

    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_1_satisfied = False
        rule3_2_satisfied = False
    elif not rule2_satisfied:
        rule3_1_satisfied = False
        rule3_2_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.25
    if rule2_satisfied:
        max_score = 0.5
    if rule3_1_satisfied or rule3_2_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 搜索国航航班",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 确认头等舱信息",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        }
    ]

    if rule2_satisfied:
        if rule3_1_satisfied:
            details.append({
                "rule": "3.1 完成购票与支付",
                "score": 1.0,
                "satisfied": True,
                "evidence": rule3_1_evidence
            })
        elif rule3_2_satisfied:
            details.append({
                "rule": "3.2 查看高铁时刻表",
                "score": 1.0,
                "satisfied": True,
                "evidence": rule3_2_evidence
            })
        else:
            details.append({
                "rule": "3.1 完成购票与支付",
                "score": 1.0,
                "satisfied": False,
                "evidence": "未完成购票或查看高铁时刻表"
            })
    else:
        details.append({
            "rule": "3.1 完成购票与支付",
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
    result = evaluate_trajectory(path="BMK/2026-04-29/携程旅行/BMK评测/7be055fc-3212-4365-892b-9bbf0d2d579e")
    print(json.dumps(result, ensure_ascii=False, indent=2))
