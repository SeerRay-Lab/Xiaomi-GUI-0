import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "小红书搜索一下北京的黑珍珠餐厅推荐，找三家川菜相关的，然后高德地图收藏距离颐和园最近的那一家"
TASK_ID = 14
STEPRULES = """评分规则（分阶段验证进度）

1. 打开小红书App，搜索北京的黑珍珠餐厅推荐 → 总分:0.25

2. 找到三家川菜相关的餐厅 → 总分:0.5

3. 打开高德地图App → 总分:0.75

4. 收藏距离颐和园最近的那一家餐厅 → 总分:1.0

一票否决条件：
- 未搜索黑珍珠或北京相关内容 → 分数:0
- 未找到川菜餐厅 → 分数:0

规则特点：
- 支持多XPath匹配，一个页面可匹配多条xpath
- 不使用break，使用布尔列表完整检查
- 完整的错误处理
"""


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
    # 一票否决条件1: 未搜索黑珍珠或北京相关内容
    has_xhs = False
    has_black_pearl = False
    has_beijing = False
    has_restaurant = False

    # 一票否决条件2: 未找到川菜餐厅
    sichuan_count = 0
    sichuan_keywords = ['川菜', '川料理', '四川菜', '麻辣', '川式']

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)

            # 检查是否是小红书
            for elem in root.iter():
                package = elem.get('package', '')
                if 'xhs' in package:
                    has_xhs = True

            # 检查是否包含黑珍珠、北京、餐厅相关关键词
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                if '黑珍珠' in combined or 'Black Pearl' in combined.lower():
                    has_black_pearl = True

                if '北京' in combined or '北京市' in combined:
                    has_beijing = True

                if '餐厅' in combined or '饭店' in combined or '餐馆' in combined or '美食' in combined:
                    has_restaurant = True

                # 计算川菜相关内容出现次数
                for keyword in sichuan_keywords:
                    if keyword in combined:
                        sichuan_count += 1
        except Exception as e:
            pass

    # 检查否决条件1：未搜索黑珍珠或北京相关内容
    if not (has_xhs and has_black_pearl and has_beijing and has_restaurant):
        return True, "未搜索黑珍珠或北京相关内容"

    # 检查否决条件2：未找到川菜餐厅
    if sichuan_count < 3:
        return True, f"未找到三家川菜餐厅（仅识别到{max(0, sichuan_count)}家）"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书App，搜索北京的黑珍珠餐厅推荐"""
    rule1_xpaths = [
        "//*[contains(@package, 'xhs')]",
        "//*[(contains(@text, '黑珍珠') or contains(@ocr_texts, '黑珍珠'))]",
        "//*[(contains(@text, '北京') or contains(@ocr_texts, '北京'))]",
        "//*[(contains(@text, '餐厅') or contains(@ocr_texts, '餐厅') or contains(@text, '饭店') or contains(@ocr_texts, '饭店'))]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
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

    # 需要同时满足：打开小红书、搜索黑珍珠、搜索北京、搜索餐厅
    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书搜索北京黑珍珠餐厅推荐"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开小红书或未搜索北京黑珍珠餐厅推荐"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：找到三家川菜相关的餐厅"""
    sichuan_keywords = ['川菜', '川料理', '四川菜', '麻辣', '川式']

    # 分支规则1: 通过xpath匹配川菜相关关键词
    branch1_xpaths = [
        "//*[(contains(@text, '川菜') or contains(@ocr_texts, '川菜'))]",
        "//*[(contains(@text, '川料理') or contains(@ocr_texts, '川料理'))]",
        "//*[(contains(@text, '四川') or contains(@ocr_texts, '四川'))]",
        "//*[(contains(@text, '麻辣') or contains(@ocr_texts, '麻辣'))]"
    ]

    checked = [False] * len(branch1_xpaths)
    evidence_steps = []
    sichuan_count = 0

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查xpath匹配（分支规则1）
        for xpath_idx in range(len(branch1_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = branch1_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    sichuan_count += 1
            except Exception as e:
                pass

        # 分支规则2: 从页面文本中计算川菜相关内容的出现次数
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                resource_id = elem.get('resource-id', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否是内容卡片或列表项（潜在的餐厅项）
                if (resource_id and ('item' in resource_id or 'card' in resource_id or 'feed' in resource_id)) or \
                   ((text and len(text) > 15) or (ocr_texts and len(ocr_texts) > 15)):
                    # 检查是否包含川菜相关关键词
                    for keyword in sichuan_keywords:
                        if keyword in combined:
                            sichuan_count += 1
        except Exception as e:
            pass

    # 至少需要找到3家川菜相关餐厅
    if sichuan_count >= 3:
        return True, f"步骤{sorted(set(evidence_steps))}: 找到{sichuan_count}家川菜相关餐厅"

    if sichuan_count > 0:
        return False, f"仅找到{sichuan_count}家川菜相关餐厅，需要3家"

    return False, "未找到川菜相关餐厅"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开高德地图App"""
    rule3_xpaths = [
        "//*[contains(@package, 'amap') or contains(@package, 'com.autonavi')]"
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
            except Exception as e:
                pass

    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开高德地图"

    return False, "未打开高德地图"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：收藏距离颐和园最近的那一家餐厅"""
    # 分支规则1: 检查收藏操作 + 颐和园/距离相关信息
    branch1_xpaths = [
        "//*[(contains(@text, '收藏') or contains(@ocr_texts, '收藏')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '颐和园') or contains(@ocr_texts, '颐和园')) ]",
    ]

    # 分支规则2: 检查高德地图中的收藏和位置信息
    branch2_xpaths = [
        "//*[(contains(@text, '收藏') or contains(@ocr_texts, '收藏')) and contains(@package, 'amap')]",
        "//*[(contains(@text, '★') or contains(@ocr_texts, '★') or contains(@text, '收藏') or contains(@ocr_texts, '收藏'))]"
    ]

    checked_branch1 = [False] * len(branch1_xpaths)
    checked_branch2 = [False] * len(branch2_xpaths)
    evidence_steps = []
    keywords_found = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查分支1的xpath匹配
        for xpath_idx in range(len(branch1_xpaths)):
            if checked_branch1[xpath_idx]:
                continue

            xpath = branch1_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked_branch1[xpath_idx] = True
                    evidence_steps.append(i)
                    if xpath_idx == 0:
                        keywords_found.append('收藏')
                    elif xpath_idx == 1:
                        keywords_found.append('颐和园')
            except Exception as e:
                pass

        # 检查分支2的xpath匹配
        for xpath_idx in range(len(branch2_xpaths)):
            if checked_branch2[xpath_idx]:
                continue

            xpath = branch2_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked_branch2[xpath_idx] = True
                    evidence_steps.append(i)
                    if xpath_idx == 0:
                        keywords_found.append('高德收藏')
                    elif xpath_idx == 1:
                        keywords_found.append('收藏标记')
            except Exception as e:
                pass

        # 分支规则3: 从页面文本内容中提取关键信息
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否包含收藏、颐和园、距离相关信息
                has_collection = '收藏' in combined or '★' in combined or '喜欢' in combined
                has_yiheyuan = '颐和园' in combined or '颐和' in combined
                has_distance = '距离' in combined or 'km' in combined or '米' in combined

                if has_collection and (has_yiheyuan or has_distance):
                    if '收藏完成' not in keywords_found:
                        keywords_found.append('收藏完成')
                        evidence_steps.append(i)
        except Exception as e:
            pass

    # 满足分支规则即可给分：需要有收藏操作 + 颐和园/距离信息
    has_collection = any(kw in keywords_found for kw in ['收藏', '高德收藏', '收藏标记', '收藏完成'])
    has_location = any(kw in keywords_found for kw in ['颐和园', '距离'])

    if has_collection and has_location:
        return True, f"步骤{sorted(set(evidence_steps))}: 收藏距离颐和园最近的餐厅（{','.join(set(keywords_found))}）"

    if has_collection or has_location:
        return False, f"仅识别到部分操作: {','.join(set(keywords_found))}"

    return False, "未找到收藏操作或位置信息"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 14,
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
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)

    details = [
        {
            "rule": "打开小红书App，搜索北京的黑珍珠餐厅推荐",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "找到三家川菜相关的餐厅",
            "score": 0.5 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "打开高德地图App",
            "score": 0.75 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "收藏距离颐和园最近的那一家餐厅",
            "score": 1.0 if rule4_satisfied else 0.0,
            "satisfied": rule4_satisfied,
            "evidence": rule4_evidence
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
        "BMK/first/6c6b06e4",
        "BMK/2026-04-29/小红书_高德地图/BMK评测/e4a542fe-4e40-4611-91b0-34f0458103b1",
        "BMK/second/5b500ee7",
        "BMK/third/93718a6b",
        "BMK/fourth/f0119320"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
