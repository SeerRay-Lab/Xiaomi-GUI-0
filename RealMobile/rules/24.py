import json
import os
import sys
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "帮我在携程买一张明天14点左右，北京到天津的高铁票"
TASK_ID = 24
STEPRULES = """分段评分规则（4阶段）

1. 打开携程 → 总分:0.25

2. 选择出发地（北京）和目的地（天津） → 总分:0.5

3. 选择日期和时间（明天14点左右） → 总分:0.75

4. 完成购票操作,点击购买按钮 → 总分:1.0

一票否决条件：
- 未打开携程 → 分数:0
- 出发地或目的地设置错误 → 分数:0
- 日期或时间设置不符合要求 → 分数:0
- 未完成购票 → 分数:0"""


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


def is_tomorrow_date(text: str) -> bool:
    """检查文本中是否包含明天的日期标识"""
    tomorrow_patterns = [
        r'明天',
        r'tomorrow',
        r'^(?P<month>\d{1,2})[/\-年](?P<day>\d{1,2})',  # 日期格式
    ]

    for pattern in tomorrow_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def is_afternoon_time(text: str) -> bool:
    """检查文本中是否包含14点左右的时间"""
    time_patterns = [
        r'14',
        r'13',
        r'15',
        r'下午[12]',
        r'下午2',
        r'下午1[3-4]',
        r'14:',
        r'14点',
        r'14时',
        r'2(点|时)?[pP][mM]',
    ]

    for pattern in time_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def is_high_speed_rail(text: str) -> bool:
    """检查文本中是否包含高铁或动车"""
    rail_patterns = [
        r'高铁',
        r'动车',
        r'[GD]\d{3,5}',  # 高铁列车号 G200, D2000等
        r'复兴号',
    ]

    for pattern in rail_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    # 一票否决1：未打开携程或未进入高铁购票
    ctrip_found = False
    high_speed_rail_page_found = False

    # 一票否决2：出发地或目的地设置错误
    beijing_found = False
    tianjin_found = False

    # 一票否决3：日期或时间设置不符合要求
    tomorrow_found = False
    time_found = False

    # 一票否决4：未完成购票
    purchase_found = False

    for xml_string in xml_strings:
        text_content = extract_text_content(xml_string)

        # 检查携程
        if not ctrip_found:
            ctrip_xpaths = [
                "//*[contains(@package, 'ctrip')]",
                "//*[contains(@package, 'trip')]",
                "//*[contains(@text, '携程') or contains(@ocr_texts, '携程')]",
                "//*[contains(@text, '携程旅行') or contains(@ocr_texts, '携程旅行')]"
            ]

            for xpath in ctrip_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                    if match_flag == 1:
                        ctrip_found = True
                        break
                except:
                    pass

        # 检查高铁购票页面
        if not high_speed_rail_page_found:
            rail_xpaths = [
                "//*[contains(@text, '高铁') or contains(@ocr_texts, '高铁')]",
                "//*[contains(@text, '火车') or contains(@ocr_texts, '火车')]",
                "//*[contains(@text, '列车') or contains(@ocr_texts, '列车')]",
                "//*[contains(@text, '购票') or contains(@ocr_texts, '购票')]",
                "//*[contains(@text, '买票') or contains(@ocr_texts, '买票')]",
            ]

            for xpath in rail_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                    if match_flag == 1:
                        high_speed_rail_page_found = True
                        break
                except:
                    pass

        # 检查北京和天津
        if not beijing_found:
            beijing_xpaths = [
                "//*[contains(@text, '北京') or contains(@ocr_texts, '北京')]",
                "//*[contains(@text, '京') or contains(@ocr_texts, '京')]",
            ]
            for xpath in beijing_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                    if match_flag == 1:
                        beijing_found = True
                        break
                except:
                    pass

        if not tianjin_found:
            tianjin_xpaths = [
                "//*[contains(@text, '天津') or contains(@ocr_texts, '天津')]",
                "//*[contains(@text, '津') or contains(@ocr_texts, '津')]",
            ]
            for xpath in tianjin_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                    if match_flag == 1:
                        tianjin_found = True
                        break
                except:
                    pass

        # 检查明天和14点左右
        if not tomorrow_found and is_tomorrow_date(text_content):
            tomorrow_found = True

        if not time_found and is_afternoon_time(text_content):
            time_found = True

        # 检查购票操作
        if not purchase_found:
            purchase_xpaths = [
                "//*[contains(@text, '购买') or contains(@ocr_texts, '购买')]",
                "//*[contains(@text, '订') or contains(@ocr_texts, '订')]",
                "//*[contains(@text, '支付') or contains(@ocr_texts, '支付')]",
            ]

            for xpath in purchase_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, xpath, {})
                    if match_flag == 1:
                        purchase_found = True
                        break
                except:
                    pass

    # 检查一票否决条件
    if not ctrip_found or not high_speed_rail_page_found:
        reason = "未打开携程或未进入高铁购票"
        if not ctrip_found:
            reason += "（未打开携程）"
        if not high_speed_rail_page_found:
            reason += "（未进入高铁购票）"
        return True, reason

    if not beijing_found or not tianjin_found:
        reason = "出发地或目的地设置错误"
        if not beijing_found:
            reason += "（未设置北京为出发地）"
        if not tianjin_found:
            reason += "（未设置天津为目的地）"
        return True, reason

    if not tomorrow_found or not time_found:
        reason = "日期或时间设置不符合要求"
        if not tomorrow_found:
            reason += "（未设置明天）"
        if not time_found:
            reason += "（未设置14点左右）"
        return True, reason

    if not purchase_found:
        return True, "未完成购票"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开携程"""
    rule1_xpath = "//*[contains(@package, 'ctrip')]"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule1_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开携程"

    return False, "未打开携程"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：选择出发地（北京）和目的地（天津）"""
    rule2_xpaths = [
        "//*[contains(@text, '北京') and contains(@resource-id, 'depart_station')] and //*[contains(@text, '天津') and contains(@resource-id, 'arrive_station')]",
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

    # 需要有北京和天津
    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 选择北京和天津"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未设置出发地或目的地"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：选择日期和时间（明天14点左右）"""
    rule3_xpaths = [
        "//*[contains(@text, '北京')] and //*[contains(@text, '天津') ] and //*[contains(@text, '明天')] ",
        "//*[contains(@text, '北京') and contains(@resource-id, 'depart_station')] and //*[contains(@text, '天津') and contains(@resource-id, 'arrive_station')] and //*[contains(@text, '14') and (contains(@resource-id, 'depart_time') or contains(@resource-id, 'arrive_time')  )] ",
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


    # 需要有明天和14点
    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 选择明天14点左右"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未设置日期或时间"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：完成购票操作,点击购买按钮"""
    rule4_xpath = "//*[contains(@text, '北京') and contains(@resource-id, 'depart_station')] and //*[contains(@text, '天津') and contains(@resource-id, 'arrive_station')] and //*[contains(@text, '14') and (contains(@resource-id, 'depart_time') or contains(@resource-id, 'arrive_time')  )] and (//*[(contains(@text, '购') or contains(@text, '买') or contains(@text, '订')) and bbox_contains_point(../../../@bounds, $point)] or  //*[contains(@text, '支付')]  )"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule4_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 完成购票操作,点击购买按钮"

    return False, "未完成购票操作"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 24,
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

    # 规则之间有依赖关系
    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule3_satisfied:
        rule4_satisfied = False

    # 计算总分
    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.25
    if rule2_satisfied:
        max_score = 0.5
    if rule3_satisfied:
        max_score = 0.75
    if rule4_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 打开携程",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 选择出发地（北京）和目的地（天津）",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 选择日期和时间（明天14点左右）",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 完成购票操作,点击购买按钮",
            "score": 1.0,
            "satisfied": rule4_satisfied,
            "evidence": rule4_evidence
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
    # 支持5个path的多路径测试
    test_paths = [
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a891013d",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/c40f605e",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/826bdc6c",
        "/main/guiagent/xiaoaidata/BMK/mai-ui/2361f1da",
        "/main/guiagent/xiaoaidata/BMK/autoglm-phone/356f07f7"
        "BMK/first/7fc85e8e",
        "BMK/2026-04-29/携程旅行/BMK评测/bf0a4584-4e02-4a6d-a154-356eddb8c424",
        "BMK/second/5d74af29",
        "BMK/third/facc88f0",
        "BMK/fourth/ef5b881b"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
