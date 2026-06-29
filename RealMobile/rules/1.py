import json                         
import os                                                                                                                                           
import sys                                                                                                                                          
from typing import Dict, List, Any, Tuple                                                                                                           
                                                                                                                                                    
# 导入已有的工具函数                                                                                                                              
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "关闭b站后台播放"
TASK_ID = 1
STEPRULES = '''打开哔哩哔哩App，进入"我的/账号"-"设置/播放设置"页面 → 总分:0.33
在设置中定位"后台播放/后台音频/小窗播放/画中画"等相关选项，判断是否可在App内直接关闭 → 总分:0.66
若在App内可设置：关闭"后台播放"（必要时一并关闭"小窗播放/画中画"等关联项） → 总分:1.0
若App内无该选项或关闭后仍会后台播放：前往手机系统设置中，找到哔哩哔哩，关闭后台音频/画中画/后台应用刷新/悬浮窗等相关权限 → 总分:1.0'''


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """加载轨迹数据，自动处理 _ocr.xml 后缀"""
    task_json_path = os.path.join(path, 'task.json')
    with open(task_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    steps = data['data']
    xml_strings = []
    actions = []

    for step in steps:
        # 将 "9.xml" 替换为 "9_ocr.xml"
        xml_file = step['xml'].replace('.xml', '_ocr.xml')
        xml_path = os.path.join(path, xml_file)
        # 如果 _ocr.xml 不存在，则使用原始文件
        if not os.path.exists(xml_path):
            xml_file = step['xml']
            xml_path = os.path.join(path, xml_file)

        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_strings.append(f.read())


        # 构造 action_dict 格式
        position_temp=step['pixel']
        if "position" in step["plan"]:
            position_temp=[int(step['pixel'][0]*step['plan']['position'][0]), int(step['pixel'][1]*step['plan']['position'][1] ) ]
        action_dict = {
            "action": "click",
            "params": {"position": position_temp}
        }
        actions.append(action_dict)

    return xml_strings, actions


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开哔哩哔哩App，进入"我的/账号"-"设置/播放设置"页面"""
    rule1_xpaths = [
        "//*[contains(@package, 'bilibili') or contains(@text, '哔哩哔哩') or contains(@ocr_texts, '哔哩哔哩')]",
        "//*[contains(@text, '我的') or contains(@ocr_texts, '我的') or contains(@text, '账号') or contains(@ocr_texts, '账号')]",
        "//*[contains(@text, '设置') or contains(@ocr_texts, '设置')]",
        "//*[contains(@text, '播放设置') or contains(@ocr_texts, '播放设置')]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidences = []

    # 从新到旧遍历历史记录
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        # 从最新到最旧匹配XPath
        for xpath_idx in range(len(rule1_xpaths) - 1, -1, -1):
            xpath = rule1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
            if match_flag == 1:
                checked[xpath_idx] = True
                evidences.append(f"第{i}步")
                break

        if all(checked):
            return True, f"满足规则1: {','.join(evidences)}"
    if not any(checked):
        return False, "未找到相关步骤"

    return False, f"部分步骤不满足: {sum(checked)}/{len(rule1_xpaths)}"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：定位后台播放相关选项"""
    rule2_xpaths = [
        "//*[contains(@text, '后台播放') or contains(@ocr_texts, '后台播放') or contains(@text, '后台音频') or contains(@ocr_texts, '后台音频') or contains(@text, '小窗播放') or contains(@ocr_texts, '小窗播放') or contains(@text, '画中画') or contains(@ocr_texts, '画中画')]"
    ]

    # 从新到旧遍历历史记录
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]
        xpath = rule2_xpaths[0]

        match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
        if match_flag == 1:
            return True, f"第{i}步找到相关选项"

    return False, "未找到后台播放相关选项"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：关闭后台播放"""
    rule3_xpaths = [
        "//*[(contains(@text, '后台播放') or contains(@ocr_texts, '后台播放')  or contains(@ocr_texts, '后台听视频') or contains(@text, '后台播放')) and bbox_contains_point(@bounds, $point) ]",
        "//*[(contains(@text, '后台播放') or contains(@ocr_texts, '后台播放')  or contains(@ocr_texts, '后台听视频') or contains(@text, '后台播放')) and @checked='false' ]",
        "//*[./*/*[contains(@text, '后台听视频')] and ./*/*[@checkable='true' and @checked='false']]"
    ]

    checked = [False] * len(rule3_xpaths)

    # 从新到旧遍历历史记录
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        # 从最新到最旧匹配XPath
        for xpath_idx in range(len(rule3_xpaths) - 1, -1, -1):
            xpath = rule3_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
            if match_flag == 1:
                checked[xpath_idx] = True
                break

        if any(checked):
            return True, f"第{i}步执行了关闭操作"

    return False, "未检测到关闭后台播放的操作"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：前往系统设置关闭权限"""
    rule4_xpaths = [
        "//*[contains(@package, 'settings') and contains(@text, '设置')]",
        "//*[contains(@text, '哔哩哔哩') or contains(@text, 'bilibili') or contains(@ocr_texts, '哔哩哔哩')]",
        "//*[(contains(@text, '后台音频') or contains(@text, '后台播放')) and bbox_contains_point(@bounds, $point)]"
    ]

    checked = [False] * len(rule4_xpaths)

    # 从新到旧遍历历史记录
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        # 从最新到最旧匹配XPath
        for xpath_idx in range(len(rule4_xpaths) - 1, -1, -1):
            xpath = rule4_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
            if match_flag == 1:
                checked[xpath_idx] = True
                break

        if sum(checked) >= 2:  # 至少满足进入系统设置和找到相关权限
            return True, f"第{i}步在系统设置中关闭权限"

    return False, "未在系统设置中关闭权限"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "关闭b站后台播放",
            "id": 1,
            "path": "BMK/...",
            "steprules": "打开哔哩哔哩App...",
            "total_score": 1.0,
            "details": [
                {
                    "rule": "打开哔哩哔哩App，进入...",
                    "score": 0.33,
                    "satisfied": True
                },
                ...
            ]
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
            "details": []
        }

    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)

    details = [
        {
            "rule": '打开哔哩哔哩App，进入"我的/账号"-"设置/播放设置"页面',
            "score": 0.33 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence":rule1_evidence
        },
        {
            "rule": '在设置中定位"后台播放/后台音频/小窗播放/画中画"等相关选项',
            "score": 0.33 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence":rule2_evidence
        },
        {
            "rule": '若在App内可设置：关闭"后台播放"',
            "score": 0.34 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence":rule3_evidence
        },
        {
            "rule": '若App内无该选项或关闭后仍会后台播放：前往手机系统设置中关闭权限',
            "score": 0.34 if rule4_satisfied else 0.0,
            "satisfied": rule4_satisfied,
            "evidence":rule4_evidence
        }
    ]

    # 最终总分 = rule1 + rule2 + max(rule3, rule4)
    total_score = 0.0
    rule1_score = 0.33 if rule1_satisfied else 0.0
    rule2_score = 0.33 if rule2_satisfied else 0.0
    rule3_score = 0.34 if rule3_satisfied else 0.0
    rule4_score = 0.34 if rule4_satisfied else 0.0

    total_score = rule1_score + rule2_score + max(rule3_score, rule4_score)

    return {
        "query": QUERY,
        "id": TASK_ID,
        "path": path,
        "steprules": STEPRULES,
        "total_score": total_score,
        "details": details
    }


if __name__ == "__main__":
    paths = [
        "BMK/first/67037d53",
        "BMK/2026-04-29/b站/BMK评测/b050bb51-3678-4374-a71f-f9bb6883c0db",
        "BMK/second/c6c2b2d1",
        "BMK/third/fb544beb",
        "BMK/fourth/6a570b1d"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))