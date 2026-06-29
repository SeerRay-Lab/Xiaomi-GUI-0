import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "查看抖音的音乐榜单的前三首歌，用汽水音乐收藏这些歌曲"
TASK_ID = 22
STEPRULES = """分段评分规则（4阶段）

1. 打开抖音 → 总分:0.25

2. 进入音乐榜单，查看榜单的前三首歌 → 总分:0.5

3. 打开汽水音乐 → 总分:0.75

4. 收藏这些歌曲 → 总分:1.0

一票否决条件：
- 未在抖音上查看音乐榜单 → 分数:0
- 未打开汽水音乐 → 分数:0"""


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


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件：
    1. 未在抖音上查看音乐榜单
    2. 未打开汽水音乐
    """
    douyin_found = False
    music_found = False
    qishui_found = False

    # 一票否决条件1：未在抖音上查看音乐榜单
    douyin_xpath = "//*[contains(@package, 'aweme')]"
    music_xpath = "//*[contains(@text, '音乐')]"

    # 一票否决条件2：未打开汽水音乐
    qishui_xpath = "//*[contains(@package, 'luna.music')]"

    for xml_string in xml_strings:
        # 检查抖音
        if not douyin_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, douyin_xpath, {})
                if match_flag == 1:
                    douyin_found = True
            except:
                pass

        # 检查音乐
        if not music_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, music_xpath, {})
                if match_flag == 1:
                    music_found = True
            except:
                pass

        # 检查汽水音乐
        if not qishui_found:
            try:
                match_flag, _ = evaluate_action_xml(xml_string, qishui_xpath, {})
                if match_flag == 1:
                    qishui_found = True
            except:
                pass

    # 检查一票否决条件1
    if not (douyin_found and music_found):
        reason = "未在抖音上查看音乐榜单"
        if not douyin_found:
            reason += "（未打开抖音）"
        if not music_found:
            reason += "（未找到音乐）"
        return True, reason

    # 检查一票否决条件2
    if not qishui_found:
        return True, "未打开汽水音乐"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音"""
    rule1_xpath = "//*[contains(@package, 'aweme')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开抖音"

    return False, "未打开抖音"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：进入音乐榜单，查看榜单的前三首歌"""
    rule2_xpath = "//*[contains(@package, 'aweme') and contains(@text, '音乐榜')] and //*[contains(@text, '热歌')] and //*[contains(@text, '飙升')]"
    evidence_steps = []
    song_count = 0

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule2_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

        # 提取文本内容检查排名信息
        try:
            text_content = extract_text_content(xml_string)
            # 检查是否包含前三首歌的排名标记
            rank_patterns = [
                ('第1', '第一', '1.', '1)', '01.'),
                ('第2', '第二', '2.', '2)', '02.'),
                ('第3', '第三', '3.', '3)', '03.')
            ]
            for idx, rank_group in enumerate(rank_patterns):
                for rank in rank_group:
                    if rank in text_content:
                        song_count = max(song_count, idx + 1)
        except:
            pass

    # 需要找到至少3首歌的排名信息
    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 查看榜单前三首歌"

    if evidence_steps or song_count > 0:
        return False, f"部分条件满足: 找到{song_count}/3首歌"

    return False, "未查看榜单前三首歌"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开汽水音乐"""
    rule3_xpath = "//*[contains(@package, 'luna.music')]"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule3_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开汽水音乐"

    return False, "未打开汽水音乐"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：收藏这些歌曲
    找到3个//*[contains(@package, 'luna.music') and contains(@resource-id, 'search')]的keyword，
    并且这些keyword在//*[contains(@package, 'aweme')]的页面中出现
    """
    luna_search_xpath = "//*[contains(@package, 'luna.music') and (contains(@resource-id, 'search') or contains(@class, 'AutoCompleteText'))]"
    aweme_xpath = "//*[contains(@package, 'aweme')]"

    # 从汽水音乐搜索结果中提取keyword
    luna_keywords = []
    aweme_found_steps = []

    # 第一阶段：在汽水音乐的搜索结果中找keyword（提取所有找到的keyword）
    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        try:
            match_flag, _ = evaluate_action_xml(xml_string, luna_search_xpath, {})
            if match_flag == 1:
                # 从搜索结果中提取文本作为keyword
                text_content = extract_text_content(xml_string)
                # 从搜索结果页面提取所有可用的文本作为keyword
                if text_content.strip():
                    words = text_content.split()
                    for word in words:
                        if len(word) > 1 and word not in luna_keywords:
                            luna_keywords.append(word)
        except:
            pass

    # 第二阶段：验证这些keyword是否在抖音页面中出现（至少3个匹配即可）
    checked = [False] * len(luna_keywords)  # 追踪每个keyword是否在抖音中找到
    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        try:
            match_flag, _ = evaluate_action_xml(xml_string, aweme_xpath, {})
            if match_flag == 1:
                aweme_found_steps.append(i)
                text_content = extract_text_content(xml_string)
                # 检查keyword是否在抖音页面中出现
                for key_idx, keyword in enumerate(luna_keywords):
                    if not checked[key_idx]:
                        if keyword in text_content:
                            checked[key_idx] = True
        except:
            pass
    print("luna_keywords",luna_keywords)
    # 需要找到至少3个keyword在抖音页面中的证据
    verified_count = sum(checked)
    evidence_steps = sorted(set(aweme_found_steps))

    if verified_count >= 3 and evidence_steps:
        return True, f"步骤{evidence_steps}: 收藏歌曲（验证{verified_count}/3个keyword）"

    if verified_count > 0 or luna_keywords:
        return False, f"部分条件满足: 验证{verified_count}/3个keyword，找到{len(luna_keywords)}个keyword"

    return False, "未进行歌曲收藏操作"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 22,
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
            "rule": "1. 打开抖音，进入音乐榜单",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 找到/查看榜单的前三首歌",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 打开汽水音乐",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 收藏这些歌曲",
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
        "BMK/first/44172d64",
        "BMK/2026-04-29/抖音_汽水音乐/BMK评测/9b847ff4-adbd-4d6b-9873-c764ad06d44f",
        "BMK/second/818dff2c",
        "BMK/third/076ba41c",
        "BMK/fourth/d721b026"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
