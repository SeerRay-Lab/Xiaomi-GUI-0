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
QUERY = "打开QQ音乐，搜索歌曲周杰伦的青花瓷、林俊杰演唱的科目三和陈奕迅的孤勇者，将它们依次加入我的喜欢"
TASK_ID = 7
STEPRULES = """评分规则

打开QQ音乐App → 总分:0.2

搜索"青花瓷 周杰伦"，找到对应歌曲并加入"我的喜欢" → 总分:0.5

搜索"科目三 林俊杰"，找到对应歌曲并加入"我的喜欢" → 总分:0.8

搜索"孤勇者 陈奕迅"，找到对应歌曲并加入"我的喜欢" → 总分:1.0

一票否决

未打开QQ音乐App → 总分:0

添加了错误的歌曲（不是指定的歌曲或歌手） → 总分:0

未完成全部三首歌的添加 → 总分:0"""


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
    # 检查是否打开了QQ音乐
    has_qqmusic = False
    has_three_songs = 0

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]

        # 检查QQ音乐
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'qqmusic') or contains(@text, 'QQ音乐') or contains(@ocr_texts, 'QQ音乐')]", action_dict)
            if match_flag == 1:
                has_qqmusic = True
        except:
            pass

        # 检查三首歌
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            if evaluate_action_xml(xml_string, "//*[contains(@text, '青花瓷') or contains(@ocr_texts, '青花瓷')]", action_dict)[0] == 1:
                has_three_songs += 1
        except:
            pass

        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            if evaluate_action_xml(xml_string, "//*[contains(@text, '科目三') or contains(@ocr_texts, '科目三')]", action_dict)[0] == 1:
                has_three_songs += 1
        except:
            pass

        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            if evaluate_action_xml(xml_string, "//*[contains(@text, '孤勇者') or contains(@ocr_texts, '孤勇者')]", action_dict)[0] == 1:
                has_three_songs += 1
        except:
            pass

    if not has_qqmusic:
        return True, "未打开QQ音乐App"

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
            except:
                pass

        if all(checked):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开QQ音乐App"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开QQ音乐App"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：搜索"青花瓷 周杰伦"，找到对应歌曲并加入"我的喜欢"""
    rule2_xpaths = [
        "//*[contains(@text, '青花瓷') or contains(@ocr_texts, '青花瓷')]",
        "//*[contains(@text, '周杰伦') or contains(@ocr_texts, '周杰伦')]",
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
            except:
                pass

        if sum(checked) >= 2:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索并添加青花瓷"

    print("rule2",checked)
    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未完成青花瓷的搜索和添加"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：搜索"科目三 林俊杰"，找到对应歌曲并加入"我的喜欢"""
    rule3_xpaths = [
        "//*[contains(@text, '科目三') or contains(@ocr_texts, '科目三')]",
        "//*[contains(@text, '林俊杰') or contains(@ocr_texts, '林俊杰')]",
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
            except:
                pass

        if sum(checked) >= 2:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索并添加科目三"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未完成科目三的搜索和添加"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：搜索"孤勇者 陈奕迅"，找到对应歌曲并加入"我的喜欢"""
    rule4_xpaths = [
        "//*[contains(@text, '孤勇者') or contains(@ocr_texts, '孤勇者')]",
        "//*[contains(@text, '陈奕迅') or contains(@ocr_texts, '陈奕迅')]",
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
            except:
                pass

        if sum(checked) >= 2:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索并添加孤勇者"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未完成孤勇者的搜索和添加"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "打开QQ音乐，搜索歌曲周杰伦的青花瓷、林俊杰演唱的科目三和陈奕迅的孤勇者，将它们依次加入我的喜欢",
            "id": 7,
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

    details = [
        {
            "rule": "打开QQ音乐App",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "搜索\"青花瓷 周杰伦\"，找到对应歌曲并加入\"我的喜欢\"",
            "score": 0.25 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "搜索\"科目三 林俊杰\"，找到对应歌曲并加入\"我的喜欢\"",
            "score": 0.25 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "搜索\"孤勇者 陈奕迅\"，找到对应歌曲并加入\"我的喜欢\"",
            "score": 0.25 if rule4_satisfied else 0.0,
            "satisfied": rule4_satisfied,
            "evidence": rule4_evidence
        }
    ]

    # 最终总分 = 所有满足的规则的分值之和
    total_score = 0.0
    for detail in details:
        if detail['satisfied']:
            total_score += detail['score']

    return {
        "query": QUERY,
        "id": TASK_ID,
        "path": path,
        "steprules": STEPRULES,
        "total_score": total_score,
        "details": details,
        "rejection_reason": None
    }


if __name__ == "__main__":
    paths = [
        "BMK/first/3082ec3c",
        "BMK/2026-04-29/qq音乐/BMK评测/e209249b-bf7f-4012-8b8e-2da348e0fe2d",
        "BMK/second/d87521b3",
        "BMK/third/88168494",
        "BMK/fourth/9ae2f982"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))