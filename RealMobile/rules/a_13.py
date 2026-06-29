import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

# 导入已有的工具函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "帮我规划一下后天全家5口人北京到天津两日游的计划，要求使用小红书查找规划，吃饭的团购券在抖音加入购物车，高铁票和酒店用qq携程买等我支付"
TASK_ID = 13
STEPRULES = """评分规则

使用小红书检索并整理"北京出发、后天起的天津两日游"方案（适合5口之家），明确行程节奏、必去景点、用餐清单与时间窗 → 总分:0.25

在抖音为所选餐厅查找匹配团购券，并按需求（覆盖5人、覆盖两日用餐次数、核对有效期包含出行日期）加入购物车 → 总分:0.5

在QQ携程搜索并选择高铁往返：后天北京→天津、次日天津→北京，5人同车次（优先连座），核对乘车人与时间匹配行程，生成待支付订单（不付款） →
总分:0.75

在QQ携程选择与行程匹配、可入住5人的酒店（1晚，家庭房或2-3间房，位置便利，优先可免费取消），提交待支付订单（不付款，等待用户支付） →
总分:1.0

一票否决


为错误城市/日期（非北京↔天津或非后天出发/次日返程）提交不可退的车票或酒店订单 → 总分:0"""


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


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""


    veto_xpaths_wrong_info = [
        # 错误城市或日期
        "//*[contains(@text, '上海') and (contains(@text, '北京') or contains(@text, '天津'))]",
        "//*[contains(@text, '今天') and (contains(@text, '出发') or contains(@text, '去程'))]",
        "//*[contains(@text, '不可退') and (contains(@text, '订单') or contains(@text, '车票'))]",
        "//*[contains(@text, '不可取消') and (contains(@text, '酒店') or contains(@text, '订单'))]"
    ]

    for xml_string in xml_strings:

        for xpath in veto_xpaths_wrong_info:
            try:
                action_dict = {"action": "click", "params": {"position": [0, 0]}}
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    return True, "检测到错误的城市/日期或不可退订单"
            except:
                pass

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：小红书规划两日游"""
    rule1_xpaths = [
        "//*[contains(@package, 'xhs') or contains(@text, '小红书')]",
        "//*[contains(@text, '北京') and contains(@text, '天津')]",
        "//*[contains(@text, '两日游') or contains(@text, '2日游')]",
        "//*[contains(@text, '攻略') or contains(@text, '行程')]",
        "//*[contains(@text, '景点') or contains(@text, '推荐')]",
        "//*[contains(@text, '5人') or contains(@text, '家庭') or contains(@text, '全家')]"
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

        if sum(checked) >= 4:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在小红书找到北京→天津两日游方案"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未在小红书规划行程"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：抖音团购券加入购物车"""
    rule2_xpaths = [
        "//*[contains(@package, 'ugc.aweme') or contains(@text, '抖音')]",
        "//*[contains(@text, '团购') or contains(@text, '优惠券')]",
        "//*[contains(@text, '餐厅') or contains(@text, '美食')]",
        "//*[(contains(@text, '购物车') or contains(@text, '加入购物车') or contains(@text, '抢购') or contains(@text, '提交成功')) and bbox_contains_point(../@bounds, $point)]",
        "//*[contains(@text, '有效期') or contains(@text, '有效') or contains(@text, '确认订单') or contains(@content-desc, '提交订单')]"
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
                    continue
            except:
                pass

        if sum(checked) >= 4:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在抖音找到团购券并加入购物车"
    print("rule2",checked)
    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未在抖音完成团购券操作"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：QQ携程高铁票预订"""
    rule3_xpaths = [
        "//*[contains(@package, 'qq') or contains(@text, '携程') or contains(@text, 'QQ携程')]",
        "//*[contains(@text, '火车票') or contains(@text, '高铁')]",
        "//*[contains(@text, '北京') and contains(@text, '天津')]",
        "//*[(contains(@text, '后天') or contains(@text, '明天')) and (contains(@text, '出发') or contains(@text, '去程'))]",
        "//*[(contains(@text, '次日') or contains(@text, '明天')) and (contains(@text, '返程') or contains(@text, '回程'))]",
        "//*[contains(@text, '5人') or contains(@text, '5张')]",
        "//*[contains(@text, '待支付') or contains(@text, '未支付')]",
        "//*[(contains(@text, '提交订单') or contains(@text, '确认订单')) and not(contains(@text, '支付'))]"
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

        if sum(checked) >= 6:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在QQ携程预订高铁票（待支付）"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未在QQ携程完成高铁预订"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：QQ携程酒店预订"""
    rule4_xpaths = [
        "//*[contains(@package, 'qq') or contains(@text, '携程') or contains(@text, 'QQ携程')]",
        "//*[contains(@text, '酒店') or contains(@text, '住宿')]",
        "//*[(contains(@text, '家庭房') or contains(@text, '2间') or contains(@text, '3间')) and contains(@text, '5人')]",
        "//*[contains(@text, '可入住5人') or contains(@text, '5人房')]",
        "//*[contains(@text, '免费取消') or contains(@text, '可取消')]",
        "//*[contains(@text, '1晚') or contains(@text, '一晚')]",
        "//*[contains(@text, '待支付') or contains(@text, '等待支付')]",
        "//*[(contains(@text, '预订') or contains(@text, '提交订单')) and not(contains(@text, '支付'))]"
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

        if sum(checked) >= 6:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在QQ携程预订酒店（待支付）"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未在QQ携程完成酒店预订"


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

    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)

    details = [
        {
            "rule": "使用小红书检索并整理\"北京出发、后天起的天津两日游\"方案",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "在抖音为所选餐厅查找团购券并加入购物车",
            "score": 0.5 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "在QQ携程搜索高铁往返并生成待支付订单",
            "score": 0.75 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "在QQ携程选择酒店并提交待支付订单",
            "score": 1.0 if rule4_satisfied else 0.0,
            "satisfied": rule4_satisfied,
            "evidence": rule4_evidence
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
        path="BMK/2026-04-29/小红书_抖音_qq_携程旅行/BMK评测/70325dd6-8f02-4a91-9783-553fc0a1e1b1"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))