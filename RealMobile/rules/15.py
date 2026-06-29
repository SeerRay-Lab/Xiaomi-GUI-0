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


QUERY = "把我的微博账号注销"
TASK_ID = 15
STEPRULES = """评分规则（分阶段验证进度）

1. 打开微博App → 总分:0.33

2. 进入账户设置/个人设置页面 → 总分:0.66

3. 找到账号注销选项 → 总分:0.85

4. 点击注销/完成注销操作 → 总分:1.0

一票否决条件：
- 未打开微博App → 分数:0
- 未进行注销操作 → 分数:0

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
    # 一票否决条件1: 未打开微博App
    has_weibo = False
    # 一票否决条件2: 未进行注销操作
    has_deregister_action = False

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否打开了微博(package包含'weibo'或'sina')
            for elem in root.iter():
                package = elem.get('package', '')
                if 'weibo' in package or 'sina' in package:
                    has_weibo = True

            # 检查是否有注销操作(包含'注销'、'注销账号'、'销户'等关键词)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                if ('注销' in combined or '注销账号' in combined or '销户' in combined or
                    '申请销号' in combined or '账号注销' in combined):
                    has_deregister_action = True
        except Exception as e:
            pass

    # 检查否决条件
    if not has_weibo:
        return True, "未打开微博App"

    if not has_deregister_action:
        return True, "未进行注销操作"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开微博App"""
    rule1_xpaths = [
        "//*[contains(@package, 'weibo') or contains(@package, 'sina')]"
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

    # 需要打开微博App
    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开微博App"

    return False, "未打开微博App"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：进入账户设置/个人设置页面"""
    rule2_xpaths = [
        "//*[(contains(@text, '设置') or contains(@ocr_texts, '设置'))]",
        "//*[(contains(@text, '账户') or contains(@ocr_texts, '账户') or contains(@text, '账号') or contains(@ocr_texts, '账号'))]",
        "//*[(contains(@text, '我') or contains(@ocr_texts, '我'))]",
        "//*[(contains(@text, '我的') or contains(@ocr_texts, '我的'))]",
        "//*[(contains(@text, '个人设置') or contains(@ocr_texts, '个人设置'))]",
        "//*[(contains(@text, '个人中心') or contains(@ocr_texts, '个人中心'))]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

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

    # 需要匹配设置相关关键词
    if sum(checked) >= 2:
        return True, f"步骤{sorted(set(evidence_steps))}: 进入账户设置/个人设置页面"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未进入账户设置页面"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：找到账号注销选项"""
    rule3_xpaths = [
        "//*[(contains(@text, '注销') or contains(@ocr_texts, '注销'))]",
        "//*[(contains(@text, '注销账号') or contains(@ocr_texts, '注销账号'))]",
        "//*[(contains(@text, '销户') or contains(@ocr_texts, '销户'))]",
        "//*[(contains(@text, '申请销号') or contains(@ocr_texts, '申请销号'))]",
        "//*[(contains(@text, '账号注销') or contains(@ocr_texts, '账号注销'))]"
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

    # 至少需要找到一个注销相关选项
    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 找到账号注销选项"

    return False, "未找到账号注销选项"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：点击注销/完成注销操作"""
    # 分支规则1: 直接点击注销按钮
    branch1_xpaths = [
        "//*[(contains(@text, '注销') or contains(@ocr_texts, '注销')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '注销账号') or contains(@ocr_texts, '注销账号')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '销户') or contains(@ocr_texts, '销户')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '申请销号') or contains(@ocr_texts, '申请销号')) and bbox_contains_point(@bounds, $point)]"
    ]

    # 分支规则2: 检查确认/完成相关文本
    branch2_xpaths = [
        "//*[(contains(@text, '确认') or contains(@ocr_texts, '确认')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '已注销') or contains(@ocr_texts, '已注销'))]",
        "//*[(contains(@text, '注销成功') or contains(@ocr_texts, '注销成功'))]",
        "//*[(contains(@text, '完成') or contains(@ocr_texts, '完成')) and bbox_contains_point(@bounds, $point)]"
    ]

    checked_branch1 = [False] * len(branch1_xpaths)
    checked_branch2 = [False] * len(branch2_xpaths)
    evidence_steps = []
    keywords_found = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查分支1的xpath匹配（点击注销按钮）
        for xpath_idx in range(len(branch1_xpaths)):
            if checked_branch1[xpath_idx]:
                continue

            xpath = branch1_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked_branch1[xpath_idx] = True
                    evidence_steps.append(i)
                    keywords_found.append('注销点击')
            except Exception as e:
                pass

        # 检查分支2的xpath匹配（确认操作或注销成功提示）
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
                        keywords_found.append('确认操作')
                    elif xpath_idx in [1, 2]:
                        keywords_found.append('注销成功')
                    elif xpath_idx == 3:
                        keywords_found.append('完成操作')
            except Exception as e:
                pass

        # 分支规则3: 从页面文本内容中提取注销相关信息
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否包含注销完成相关关键词
                if ('已注销' in combined or '注销成功' in combined or
                    '账号已注销' in combined or '注销完成' in combined):
                    if '注销完成' not in keywords_found:
                        keywords_found.append('注销完成')
                        evidence_steps.append(i)
        except Exception as e:
            pass

    # 满足条件：需要有注销点击 + 确认/完成操作
    has_deregister_click = any(kw in keywords_found for kw in ['注销点击', '注销成功', '注销完成'])
    has_confirmation = any(kw in keywords_found for kw in ['确认操作', '完成操作', '注销成功', '注销完成'])

    if has_deregister_click or has_confirmation:
        return True, f"步骤{sorted(set(evidence_steps))}: 点击注销/完成注销操作（{','.join(set(keywords_found))}）"

    return False, "未完成注销操作"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 15,
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

    # 计算总分（完成到的最高步骤的累计分值）
    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.33
    if rule2_satisfied:
        max_score = 0.66
    if rule3_satisfied:
        max_score = 0.85
    if rule4_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 打开微博App",
            "score": 0.33,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 进入账户设置/个人设置页面",
            "score": 0.66,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 找到账号注销选项",
            "score": 0.85,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 点击注销/完成注销操作",
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
    paths = [
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/3c8754a9",
        "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/50ea8ed8",
        "/main/guiagent/xiaoaidata/BMK/autoglm-phone/671b2d9e",
        "BMK/first/de19173f",
        "BMK/2026-04-29/微博/BMK评测/15c39d20-1634-415c-b6c4-d1c537344bc5",
        "BMK/second/e072af86",
        "BMK/third/8cabd215",
        "BMK/fourth/3e279dff"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
