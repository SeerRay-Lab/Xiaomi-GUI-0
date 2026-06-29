import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "请通过抖音、小红书、微博这些app帮我规划一个本周日晚上吃饭+看电影的约会"
TASK_ID = 20
STEPRULES = """1. 打开抖音，搜索餐厅或电影相关内容 → 总分:0.33

2. 打开小红书，搜索餐厅或电影推荐 → 总分:0.66

3. 打开微博，搜索相关内容 → 总分:1.0

一票否决条件：
- 未在至少两个平台上进行搜索 → 分数:0
- 未找到餐厅或电影相关信息 → 分数:0"""


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
    """检查一票否决条件：
    1. 未在至少两个平台上进行搜索
    2. 未找到餐厅或电影相关信息
    """
    # 检查平台使用情况
    douyin_found = False
    xhs_found = False
    weibo_found = False

    restaurant_or_movie_found = False

    platform_xpaths = [
        "//*[contains(@package, 'douyin') or contains(@package, 'aweme') or contains(@text, '抖音')]",
        "//*[contains(@package, 'xhs') or contains(@text, '小红书')]",
        "//*[contains(@package, 'weibo') or contains(@text, '微博')]"
    ]

    content_xpaths = [
        "//*[contains(@text, '餐厅') or contains(@text, '餐厅推荐') or contains(@text, '美食')]",
        "//*[contains(@text, '电影') or contains(@text, '电影推荐') or contains(@text, '影厅')]",
        "//*[contains(@text, '约会') or contains(@text, '晚餐')]"
    ]

    for xml_string in xml_strings:
        # 检查平台
        try:
            if not douyin_found:
                match_flag, _ = evaluate_action_xml(xml_string, platform_xpaths[0], {})
                if match_flag == 1:
                    douyin_found = True
        except:
            pass

        try:
            if not xhs_found:
                match_flag, _ = evaluate_action_xml(xml_string, platform_xpaths[1], {})
                if match_flag == 1:
                    xhs_found = True
        except:
            pass

        try:
            if not weibo_found:
                match_flag, _ = evaluate_action_xml(xml_string, platform_xpaths[2], {})
                if match_flag == 1:
                    weibo_found = True
        except:
            pass

        # 检查内容
        if not restaurant_or_movie_found:
            for content_xpath in content_xpaths:
                try:
                    match_flag, _ = evaluate_action_xml(xml_string, content_xpath, {})
                    if match_flag == 1:
                        restaurant_or_movie_found = True
                except:
                    pass

    # 一票否决条件1：未在至少两个平台上进行搜索
    platforms_used = sum([douyin_found, xhs_found, weibo_found])
    if platforms_used < 2:
        return True, f"未在至少两个平台上进行搜索（仅使用了{platforms_used}个平台）"

    # 一票否决条件2：未找到餐厅或电影相关信息
    if not restaurant_or_movie_found:
        return True, "未找到餐厅或电影相关信息"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音，搜索餐厅或电影相关内容"""
    rule1_xpaths = [
        # 抖音平台标识
        "//*[contains(@package, 'aweme') ] and //*[contains(@text, '餐厅') or contains(@text, '美食') or contains(@text, '吃饭') or contains(@text, '饭店')]  ",
        "//*[contains(@package, 'aweme') ] and //*[contains(@text, '电影') or contains(@text, '看电影') or contains(@text, '影院') or contains(@text, '影厅')]",
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(rule1_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule1_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass


    if any(checked):
        return  True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在抖音搜索餐厅或电影相关内容"

    return False, "未在抖音搜索"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开小红书，搜索餐厅或电影推荐"""
    rule2_xpaths = [
        # 小红书平台标识\
        "//*[contains(@package, 'xhs') ] and //*[contains(@text, '餐厅') or contains(@text, '美食') or contains(@text, '吃饭') or contains(@text, '饭店')]  ",
        "//*[contains(@package, 'xhs') ] and //*[contains(@text, '电影') or contains(@text, '看电影') or contains(@text, '影院') or contains(@text, '影厅')]",
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


    if any(checked):
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在小红书搜索餐厅或电影相关内容"

    return False, "未在小红书搜索"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开微博，搜索相关内容"""
    rule3_xpaths = [
        # 微博平台标识
        "//*[contains(@package, 'weibo') ] and //*[contains(@text, '餐厅') or contains(@text, '美食') or contains(@text, '吃饭') or contains(@text, '饭店')]  ",
        "//*[contains(@package, 'weibo') ] and //*[contains(@text, '电影') or contains(@text, '看电影') or contains(@text, '影院') or contains(@text, '影厅')]",
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


    if any(checked):
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 在微博搜索餐厅或电影相关内容"

    return False, "未在微博搜索"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 20,
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

    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)

    # 级联关系：上一级不满足则下一级不计分
    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False

    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.33
    if rule2_satisfied:
        max_score = 0.66
    if rule3_satisfied:
        max_score = 1.0

    details = [
        {
            "rule": "1. 在抖音搜索",
            "score": 0.33,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 在小红书搜索",
            "score": 0.66,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 在微博搜索",
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
    # 支持5个path的多路径测试
    test_paths = [
        "BMK/first/c81b5e23",
        "BMK/2026-04-29/抖音_小红书_微博/BMK评测/68f0488c-659d-4245-aca6-9af5951522a2",
        "BMK/second/715a88e9",
        "BMK/third/f593706a",
        "BMK/fourth/086700ae"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 如果路径不存在，尝试评估第一个存在的路径
            if path == test_paths[1]:
                print(f"\n评估默认路径: {path}")
                result = evaluate_trajectory(path=path)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                break
            continue
