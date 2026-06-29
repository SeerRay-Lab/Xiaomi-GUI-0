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


QUERY = "抖音搜一下小米有哪些女高管，然后去微博关注一下她们"
TASK_ID = 21
STEPRULES = """评分规则（分阶段验证进度 - 4阶段）

1. 打开抖音，搜索小米女高管 → 总分:0.25

2. 找到/查看小米女高管信息 → 总分:0.5

3. 打开微博 → 总分:0.75

4. 关注女高管账号 → 总分:1.0

一票否决条件：
- 未在抖音上搜索小米女高管 → 分数:0
- 未打开微博 → 分数:0

规则特点：
- 规则1: 检查抖音(douyin/aweme) + 搜索框 + (小米 + 女高管/女性领导/女管理等关键词)
- 规则2: 检查女高管信息出现(包含名字、职位、小米等关键词的组合)
- 规则3: 检查微博(weibo)的presence
- 规则4: 检查关注操作('关注'按钮被点击 + bbox_contains_point确认，或检测到已关注状态)
- 使用 [False] * len(xpaths) 布尔列表，不使用break
- 支持一个页面匹配多个xpath
- 完整的错误处理
- 支持多路径input
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
    # 一票否决条件1: 未在抖音上搜索小米女高管
    has_douyin = False
    has_search = False
    has_xiaomi = False
    has_female_keywords = False

    # 一票否决条件2: 未打开微博
    has_weibo = False

    female_keywords = ['女高管', '女性领导', '女管理', '女性CEO', '女性主管', '女董事', '女总裁', '女总经理', '女VP']

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)

            # 检查package和text属性
            for elem in root.iter():
                package = elem.get('package', '')
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查抖音
                if 'douyin' in package or 'aweme' in package or 'tiktok' in package:
                    has_douyin = True

                # 检查搜索框或搜索操作
                if ('搜索' in combined or '搜一下' in combined or '搜索框' in combined or
                    'search' in combined.lower() or '查一下' in combined):
                    has_search = True

                # 检查小米相关
                if '小米' in combined or 'xiaomi' in combined.lower():
                    has_xiaomi = True

                # 检查女高管相关关键词
                for keyword in female_keywords:
                    if keyword in combined:
                        has_female_keywords = True
                        break

                # 检查微博
                if 'weibo' in package or 'sina' in package:
                    has_weibo = True

        except Exception as e:
            pass

    # 检查一票否决条件1：未在抖音上搜索小米女高管
    if not (has_douyin and has_search and has_xiaomi and has_female_keywords):
        reason = "未在抖音上搜索小米女高管"
        if not has_douyin:
            reason += "（未打开抖音）"
        if not has_search:
            reason += "（未进行搜索操作）"
        if not has_xiaomi:
            reason += "（未搜索小米相关内容）"
        if not has_female_keywords:
            reason += "（未识别到女高管关键词）"
        return True, reason

    # 检查一票否决条件2：未打开微博
    if not has_weibo:
        return True, "未打开微博"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音，搜索小米女高管"""
    rule1_xpaths = [
        "//*[contains(@package, 'douyin') or contains(@package, 'aweme') or contains(@package, 'tiktok')]",
        "//*[(contains(@text, '搜索') or contains(@ocr_texts, '搜索') or contains(@text, '搜索框') or contains(@ocr_texts, '搜索框'))]",
        "//*[(contains(@text, '小米') or contains(@ocr_texts, '小米'))]",
        "//*[(contains(@text, '女高管') or contains(@ocr_texts, '女高管') or contains(@text, '女性领导') or contains(@ocr_texts, '女性领导') or contains(@text, '女管理') or contains(@ocr_texts, '女管理'))]"
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

    # 需要满足：打开抖音 + 搜索 + 小米 + 女高管关键词
    if sum(checked) >= 4:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开抖音搜索小米女高管"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未在抖音上搜索小米女高管"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：找到/查看小米女高管信息"""
    rule2_xpaths = [
        "//*[(contains(@text, '名字') or contains(@ocr_texts, '名字') or contains(@text, '姓名') or contains(@ocr_texts, '姓名'))]",
        "//*[(contains(@text, '职位') or contains(@ocr_texts, '职位') or contains(@text, 'CEO') or contains(@ocr_texts, 'CEO'))]",
        "//*[(contains(@text, '小米') or contains(@ocr_texts, '小米'))]",
        "//*[(contains(@text, '女') or contains(@ocr_texts, '女'))]",
        "//*[(contains(@text, '高管') or contains(@ocr_texts, '高管') or contains(@text, '领导') or contains(@ocr_texts, '领导'))]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []
    info_found = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
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

        # 从页面文本内容中提取信息
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否包含女高管相关信息的组合
                has_xiaomi = '小米' in combined
                has_female = '女' in combined or '女性' in combined
                has_position = ('职位' in combined or 'CEO' in combined or '总裁' in combined or
                               '总经理' in combined or '主管' in combined or '领导' in combined)
                has_name = len(text or '') > 1 or len(ocr_texts or '') > 1

                if (has_xiaomi or has_female) and (has_position or has_name):
                    if '女高管信息' not in info_found:
                        info_found.append('女高管信息')
                        evidence_steps.append(i)
        except Exception as e:
            pass

    # 至少需要识别到名字、职位、小米、女、高管等信息中的几个关键组合
    if sum(checked) >= 3 or '女高管信息' in info_found:
        return True, f"步骤{sorted(set(evidence_steps))}: 找到/查看小米女高管信息"

    if any(checked) or info_found:
        return False, f"部分信息满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未找到/查看小米女高管信息"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开微博"""
    rule3_xpaths = [
        "//*[contains(@package, 'weibo') or contains(@package, 'sina')]",
        "//*[(contains(@text, '微博') or contains(@ocr_texts, '微博'))]"
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
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

        # 至少有一个xpath匹配即可通过规则3（打开微博）
        if any(checked):
            return True, f"步骤{sorted(set(evidence_steps))}: 打开微博"

    return False, "未打开微博"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：关注女高管账号"""
    rule4_xpaths = [
        "//*[(contains(@text, '关注') or contains(@ocr_texts, '关注')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '已关注') or contains(@ocr_texts, '已关注'))]",
        "//*[(contains(@text, '关注成功') or contains(@ocr_texts, '关注成功'))]",
        "//*[(contains(@text, '+关注') or contains(@ocr_texts, '+关注'))]"
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []
    follow_keywords = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
        for xpath_idx in range(len(rule4_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule4_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    if xpath_idx == 0:
                        follow_keywords.append('关注点击')
                    elif xpath_idx == 1:
                        follow_keywords.append('已关注状态')
                    elif xpath_idx == 2:
                        follow_keywords.append('关注成功')
                    elif xpath_idx == 3:
                        follow_keywords.append('关注按钮')
            except Exception as e:
                pass

        # 从页面文本内容中提取关注相关信息
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否包含关注完成的相关关键词
                if ('已关注' in combined or '关注成功' in combined or '已成功关注' in combined):
                    if '关注完成' not in follow_keywords:
                        follow_keywords.append('关注完成')
                        evidence_steps.append(i)
        except Exception as e:
            pass

    # 至少需要识别到关注操作或已关注状态
    has_follow_action = any(kw in follow_keywords for kw in ['关注点击', '关注按钮', '关注成功', '关注完成'])
    has_follow_status = any(kw in follow_keywords for kw in ['已关注状态', '关注完成'])

    if has_follow_action or has_follow_status:
        return True, f"步骤{sorted(set(evidence_steps))}: 关注女高管账号（{','.join(set(follow_keywords))}）"

    if any(checked) or follow_keywords:
        return False, f"部分条件满足: {','.join(set(follow_keywords))}"

    return False, "未关注女高管账号"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 21,
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

    # 规则之间有依赖关系：规则1是基础，后续规则依赖前面的规则完成
    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule3_satisfied:
        rule4_satisfied = False

    # 计算总分（完成到的最高步骤的累计分值）
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
            "rule": "1. 打开抖音，搜索小米女高管",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 找到/查看小米女高管信息",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 打开微博",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 关注女高管账号",
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
    # 支持多路径测试
    test_paths = [
        "BMK/first/13ad4e60",
        "BMK/2026-04-29/抖音_微博/BMK评测/4b4ca5b8-6063-43e1-81b0-4fce2f2a03c9",
        "BMK/second/4894f1e5",
        "BMK/third/0dd60524",
        "BMK/fourth/a6c190ea"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 如果没有找到任何路径，使用第一个作为示例
            print(f"\n评估路径: {test_paths[0]}")
            result = evaluate_trajectory(path=test_paths[0])
            print(json.dumps(result, ensure_ascii=False, indent=2))
