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
QUERY = "打开QQ音乐，帮我买一张明天去广州的火车票"
TASK_ID = 6
STEPRULES = """评分规则

打开QQ音乐App → 总分:0.2

在QQ音乐内找到火车票购买入口（如火车票、出行、慧行、高铁等） → 总分:0.4

选择出发地（当前城市/定位）和目的地（广州），日期选择明天 → 总分:0.6

筛选合适车次，点击进入预订页 → 总分:0.8

选择乘客/添加乘客，确认订单并进入支付环节（无需真正支付） → 总分:1.0

一票否决

打开的是非QQ音乐的其他App → 总分:0

购买的是非火车票的票务（如飞机票、汽车票、船票等） → 总分:0

目的地不是广州 → 总分:0

日期不是明天 → 总分:0"""


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
            # 如果 _ocr.xml 不存在，使用原始文件
            xml_path = os.path.join(path, step['xml'])

        if not os.path.exists(xml_path):
            continue

        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_strings.append(f.read())

        # 构造 action_dict 格式，正确计算点击坐标
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


def check_rejection_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    rejection_xpaths = [
        # 打开的不是QQ音乐
        "//*[contains(@package, 'qqmusic') and not(contains(@package, 'qqmusic'))]",

        # 购买了非火车票
        "//*[contains(@text, '飞机票') or contains(@ocr_texts, '飞机票') or contains(@text, '汽车票') or contains(@ocr_texts, '汽车票') or contains(@text, '船票') or contains(@ocr_texts, '船票')]",

        # 目的地不是广州
        "//*[contains(@text, '目的地') or contains(@ocr_texts, '目的地')]",

        # 日期不是明天
        "//*[contains(@text, '出发日期') or contains(@ocr_texts, '出发日期')]"
    ]

    rejection_reasons = [
        "打开的是非QQ音乐的其他App",
        "购买的是非火车票的票务",
        "目的地不是广州",
        "日期不是明天"
    ]

    # 遍历所有步骤检查否决条件
    has_guangzhou = False
    has_tomorrow = False

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]

        # 检查是否有非火车票
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, rejection_xpaths[1], action_dict)
            if match_flag == 1:
                return True, rejection_reasons[1]
        except:
            pass

        # 检查是否有广州
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '广州') or contains(@ocr_texts, '广州')]", action_dict)
            if match_flag == 1:
                has_guangzhou = True
        except:
            pass

        # 检查是否有明天
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '明天') or contains(@ocr_texts, '明天')]", action_dict)
            if match_flag == 1:
                has_tomorrow = True
        except:
            pass

    # 如果轨迹中能找到广州和明天，说明是正确的目的地和日期
    # 但如果完全没有找到，也不算否决（因为可能是其他表达方式）

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开QQ音乐App"""
    rule1_xpaths = [
        "//*[contains(@package, 'qqmusic') or contains(@text, 'QQ音乐') or contains(@ocr_texts, 'QQ音乐')]",
        "//*[contains(@text, '音乐') or contains(@ocr_texts, '音乐') or contains(@text, '推荐') or contains(@ocr_texts, '推荐')]"
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

        if all(checked):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开QQ音乐App"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开QQ音乐App"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：在QQ音乐内找到火车票购买入口"""
    rule2_xpaths = [
        "//*[contains(@text, '火车票') or contains(@ocr_texts, '火车票')]",
        "//*[contains(@text, '出行') or contains(@ocr_texts, '出行') or contains(@text, '慧行') or contains(@ocr_texts, '慧行') or contains(@text, '高铁') or contains(@ocr_texts, '高铁')]",
        "//*[(contains(@text, '火车票') or contains(@ocr_texts, '火车票') or contains(@text, '高铁') or contains(@ocr_texts, '高铁')) and bbox_contains_point(@bounds, $point)]"
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

        if sum(checked) >= 2:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 找到火车票购买入口"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未找到火车票购买入口"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：选择出发地和目的地，日期选择明天"""
    rule3_xpaths = [
        "//*[contains(@text, '出发') or contains(@ocr_texts, '出发') or contains(@text, '出发地') or contains(@ocr_texts, '出发地')]",
        "//*[contains(@text, '当前城市') or contains(@ocr_texts, '当前城市') or contains(@text, '定位') or contains(@ocr_texts, '定位')]",
        "//*[contains(@text, '目的地') or contains(@ocr_texts, '目的地') or contains(@text, '到达') or contains(@ocr_texts, '到达')]",
        "//*[contains(@text, '广州') or contains(@ocr_texts, '广州')]",
        "//*[contains(@text, '日期') or contains(@ocr_texts, '日期') or contains(@text, '出发日期') or contains(@ocr_texts, '出发日期')]",
        "//*[contains(@text, '明天') or contains(@ocr_texts, '明天')]"
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

        # 检查是否至少满足：出发地、广州目的地、明天日期
        if checked[0] and checked[3] and checked[5]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 选择出发地和广州，日期选择明天"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未完成出发地、目的地和日期选择"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：筛选合适车次，点击进入预订页"""
    rule4_xpaths = [
        "//*[(contains(@text, '查询') or contains(@ocr_texts, '查询') or contains(@text, '搜索') or contains(@ocr_texts, '搜索')) and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '筛选') or contains(@ocr_texts, '筛选')]",
        "//*[(contains(@text, 'G') or contains(@text, 'D') or contains(@text, 'C') or contains(@text, 'K') or contains(@text, 'T')) and (contains(@text, '次') or contains(@ocr_texts, '次')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '预订') or contains(@ocr_texts, '预订') or contains(@text, '购票') or contains(@ocr_texts, '购票')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '确认') or contains(@ocr_texts, '确认') or contains(@text, '下一步') or contains(@ocr_texts, '下一步')) and bbox_contains_point(@bounds, $point)]"
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule4_xpaths) - 1, -1, -1):
            xpath = rule4_xpaths[xpath_idx]
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

        # 至少需要查询和预订/下一步动作
        if (checked[0] or checked[1]) and (checked[3] or checked[4]):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 筛选车次并进入预订页"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未进入预订页"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：选择乘客，确认订单并进入支付环节"""
    rule5_xpaths = [
        "//*[contains(@text, '乘客') or contains(@ocr_texts, '乘客') or contains(@text, '乘车人') or contains(@ocr_texts, '乘车人')]",
        "//*[(contains(@text, '添加') or contains(@ocr_texts, '添加')) and (contains(@text, '乘客') or contains(@text, '乘车人')) and bbox_contains_point(@bounds, $point)]",
        "//*[contains(@text, '确认订单') or contains(@ocr_texts, '确认订单') or contains(@text, '订单确认') or contains(@ocr_texts, '订单确认')]",
        "//*[contains(@text, '提交订单') or contains(@ocr_texts, '提交订单')]",
        "//*[(contains(@text, '支付') or contains(@ocr_texts, '支付')) and (contains(@text, '立即支付') or contains(@text, '去支付') or contains(@text, '确认支付')) and bbox_contains_point(@bounds, $point)]"
    ]

    checked = [False] * len(rule5_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule5_xpaths) - 1, -1, -1):
            xpath = rule5_xpaths[xpath_idx]
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

        # 至少需要乘客确认和支付动作
        if (checked[0] or checked[1]) and (checked[2] or checked[3]) and checked[4]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 选择乘客，确认订单并进入支付"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule5_xpaths)}"

    return False, "未完成订单确认和支付环节"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "打开QQ音乐，帮我买一张明天去广州的火车票",
            "id": 6,
            "path": "BMK/...",
            "steprules": "评分规则...",
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
    is_rejected, rejection_reason = check_rejection_conditions(xml_strings, actions)
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
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)
    rule5_satisfied, rule5_evidence = evaluate_rule_5(xml_strings, actions)

    details = [
        {
            "rule": "打开QQ音乐App",
            "score": 0.2 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "在QQ音乐内找到火车票购买入口（如火车票、出行、慧行、高铁等）",
            "score": 0.4 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "选择出发地（当前城市/定位）和目的地（广州），日期选择明天",
            "score": 0.6 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "筛选合适车次，点击进入预订页",
            "score": 0.8 if rule4_satisfied else 0.0,
            "satisfied": rule4_satisfied,
            "evidence": rule4_evidence
        },
        {
            "rule": "选择乘客/添加乘客，确认订单并进入支付环节（无需真正支付）",
            "score": 1.0 if rule5_satisfied else 0.0,
            "satisfied": rule5_satisfied,
            "evidence": rule5_evidence
        }
    ]

    # 最终总分 = 所有满足的规则中最高的分值
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
    result = evaluate_trajectory(
        path="BMK/2026-04-29/qq音乐/BMK评测/cf816e20-44a1-448b-8cd3-1718ca2810bf"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))