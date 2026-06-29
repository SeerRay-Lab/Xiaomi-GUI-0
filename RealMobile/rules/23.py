import json
import os
import sys
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "打开番茄小说，在完结榜上挑排名前三的小说。我不喜欢看太短的，你帮我对比一下这三本，把字数超过 200万字且在这三本里评分最高的那本小说的名字，发到qq我的电脑"
TASK_ID = 23
STEPRULES = """分段评分规则（4阶段）

1. 打开番茄小说 → 总分:0.25

2. 进入完结榜 → 总分:0.5

3. 进入QQ，向我的电脑发送信息 → 总分:0.75

4. 发送的信息关键词是完结榜里面的小说名 → 总分:1.0

一票否决条件：
- 向QQ发送消息的小说没有超过200万字，或者在这三本里评分不是最高 → 分数:0"""


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


def extract_numeric_value(text: str, pattern: str) -> Optional[float]:
    """从文本中提取数值"""
    try:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    except:
        pass
    return None


def extract_novel_info(xml_strings: List[str]) -> List[Dict[str, Any]]:
    """提取小说信息：排名、名字、字数、评分"""
    novels = []

    for xml_string in xml_strings:
        try:
            text_content = extract_text_content(xml_string)

            # 提取排名（1-3）
            rank_patterns = [
                (r'第1名|第一名|^1\.|^1\)|^1、|排名第1|排名1', 1),
                (r'第2名|第二名|^2\.|^2\)|^2、|排名第2|排名2', 2),
                (r'第3名|第三名|^3\.|^3\)|^3、|排名第3|排名3', 3),
            ]

            rank = None
            for pattern, rank_num in rank_patterns:
                if re.search(pattern, text_content):
                    rank = rank_num
                    break

            if rank is None:
                continue

            # 提取字数（万字、字 等）
            word_count = None
            # 尝试多种格式：XXX万字、XXXw、XXX万等
            word_patterns = [
                r'(\d+(?:\.\d+)?)\s*万字',
                r'(\d+(?:\.\d+)?)\s*w$',
                r'(\d+(?:\.\d+)?)\s*万',
            ]

            for pattern in word_patterns:
                word_match = re.search(pattern, text_content)
                if word_match:
                    word_count = float(word_match.group(1)) * 10000  # 转换为字数
                    break

            # 提取评分（★、分、星等）
            score = None
            score_patterns = [
                r'(\d+(?:\.\d+)?)\s*分',
                r'(\d+(?:\.\d+)?)\s*★',
                r'★+\s*(\d+(?:\.\d+)?)',
                r'评分[：:\s]*(\d+(?:\.\d+)?)',
            ]

            for pattern in score_patterns:
                score_match = re.search(pattern, text_content)
                if score_match:
                    score = float(score_match.group(1))
                    break

            if word_count is not None and score is not None:
                novels.append({
                    'rank': rank,
                    'word_count': word_count,
                    'score': score,
                    'text': text_content[:100]  # 存储部分文本用于参考
                })
        except:
            pass

    return novels


def extract_top3_novel_names(xml_strings: List[str]) -> List[str]:
    """从完结榜中提取前三本小说名"""
    novel_names = []
    rank_count = 0

    for xml_string in xml_strings:
        try:
            text_content = extract_text_content(xml_string)
            # 查找排名标记（第1、第2、第3等）
            rank_patterns = [
                (r'第\s*1\s*(.+?)(?=第\s*2|$)', 1),
                (r'第\s*2\s*(.+?)(?=第\s*3|$)', 2),
                (r'第\s*3\s*(.+?)(?=$)', 3),
            ]

            for pattern, rank in rank_patterns:
                match = re.search(pattern, text_content, re.DOTALL)
                if match:
                    novel_name = match.group(1).split('\n')[0].strip()
                    if novel_name and len(novel_name) > 0:
                        novel_names.append(novel_name)
                        rank_count += 1
        except:
            pass

    return novel_names[:3]


def check_veto_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查是否找到字数>=200万字的小说

    返回：(found_large_novel, reason)
    - found_large_novel: 是否找到了>=200万字的小说
    - reason: 如果没找到的原因
    """

    found_large_novel = False

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        try:
            root = ET.fromstring(xml_string)

            # 先检查是否在dragon.read页面
            is_dragon_read = False
            for elem in root.iter():
                package = elem.get('package', '')
                if 'dragon.read' in package:
                    is_dragon_read = True
                    break

            if not is_dragon_read:
                continue

            # 方式1：查找"万字"元素及其前一个兄弟节点（通常包含数字）
            for elem in root.iter():
                text = elem.get('text', '')
                if '万字' in text:
                    # 找这个元素的父节点，获取前一个兄弟
                    for parent in root.iter():
                        children = list(parent)
                        if elem in children:
                            elem_idx = children.index(elem)
                            # 检查前一个兄弟节点
                            if elem_idx > 0:
                                prev_sibling = children[elem_idx - 1]
                                prev_text = prev_sibling.get('text', '').strip()
                                # 提取数字
                                match = re.search(r'(\d+(?:\.\d+)?)', prev_text)
                                if match:
                                    num = float(match.group(1))
                                    if num >= 200:
                                        found_large_novel = True
                            break

            # 方式2：查找包含"XXX万字"格式的元素
            for elem in root.iter():
                text = elem.get('text', '')
                if '万字' in text:
                    match = re.search(r'(\d+(?:\.\d+)?)\s*万字', text)
                    if match:
                        num = float(match.group(1))
                        if num >= 200:
                            found_large_novel = True

        except:
            pass

    if not found_large_novel:
        return False, "未找到字数>=200万字的小说"

    return True, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开番茄小说"""
    rule1_xpath = "//*[contains(@package, 'dragon.read')]"
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
        return True, f"步骤{sorted(set(evidence_steps))}: 打开番茄小说"

    return False, "未打开番茄小说"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：进入完结榜"""
    rule2_xpath = "//*[(contains(@text, '完结') or contains(@text, '完本')) and bbox_contains_point(@bounds, $point)]"
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rule2_xpath, action_dict)
            if match_flag == 1:
                evidence_steps.append(i)
        except:
            pass

    if evidence_steps:
        return True, f"步骤{sorted(set(evidence_steps))}: 进入完结榜"

    return False, "未进入完结榜"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：进入QQ，向我的电脑发送信息"""
    rule3_xpaths = [
        "//*[contains(@package, 'mobileqq') and contains(@text, '我的电脑')]",
        "//*[contains(@text, '发送') and bbox_contains_point(@bounds, $point)]"
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

    # 需要同时满足：进入QQ我的电脑 + 发送操作
    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 进入QQ，向我的电脑发送信息"

    if any(checked):
        return False, f"部分条件满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未进入QQ或未发送信息"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：发送的信息关键词是完结榜里面的小说名"""

    # 第二步：从QQ+我的电脑页面中提取EditText的文本（keyword）
    qq_keyword = None
    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        try:
            root = ET.fromstring(xml_string)
            qq_found = False
            my_computer_found = False

            for elem in root.iter():
                package = elem.get('package', '')
                text = elem.get('text', '')

                if 'mobileqq' in package:
                    qq_found = True
                if '我的电脑' in text:
                    my_computer_found = True

            if qq_found and my_computer_found:
                # 在这个页面查找EditText元素
                for elem in root.iter():
                    elem_class = elem.get('class', '')
                    text = elem.get('text', '')
                    if 'EditText' in elem_class and text and len(text) > 1:
                        qq_keyword = text
                        break

            if qq_keyword:
                break
        except:
            pass

    if not qq_keyword:
        return False, "未找到QQ中发送的信息"

    # 第三步：检查keyword是否在dragon.read页面中出现
    # 如果keyword中有空格或《》，按这些分割后只要有一个部分匹配就行
    keyword_parts = re.split(r'[\s《》<>]+', qq_keyword)
    keyword_parts = [p for p in keyword_parts if p]  # 去掉空字符串

    matched = False
    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            package_found = False
            for elem in root.iter():
                p = elem.get('package', '')
                if 'dragon.read' in p:
                    package_found = True
                    break

            if not package_found:
                continue

            text_content = extract_text_content(xml_string)

            # 检查keyword_parts中的任何一个部分是否出现在页面中
            for part in keyword_parts:
                if part and part in text_content:
                    matched = True
                    break

            if matched:
                break
        except:
            pass

    # 需要至少有一个keyword部分在dragon.read页面中出现
    if matched:
        evidence = f"发送信息: {qq_keyword}"
        return True, f"发送的信息关键词是完结榜小说名（{evidence}）"

    return False, f"发送的信息不是完结榜小说名（发送: {qq_keyword}）"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 23,
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

    # 检查字数>=200万的小说是否存在
    found_large_novel, large_novel_reason = check_veto_conditions(xml_strings, actions)

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

    # 特殊逻辑：处理字数>=200万的条件
    # 如果找不到字数>=200万的小说：
    #   - 如果rule4触发（给QQ发送了小说名）→ total_score = 0
    #   - 如果rule4未触发（没给QQ发送）→ total_score = 1.0
    # 如果找到了字数>=200万的小说：
    #   - 按正常逻辑计算分数

    if not found_large_novel:
        if rule4_satisfied:
            # 找不到>=200万，但给QQ发送了 → 否决
            max_score = 0.0
            rejection_reason = f"{large_novel_reason}（已给QQ发送，故否决）"
        else:
            # 找不到>=200万，但没给QQ发送 → 通过
            max_score = 1.0
            rejection_reason = None
    else:
        # 正常逻辑：按规则依次计分
        max_score = 0.0
        rejection_reason = None
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
            "rule": "1. 打开番茄小说",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 进入完结榜",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 进入QQ，向我的电脑发送信息",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 发送的信息关键词是完结榜里面的小说名",
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
        "rejection_reason": rejection_reason
    }


if __name__ == "__main__":
    # 支持4个path的多路径测试
    test_paths = [
        "BMK/first/0d002bbc",
        "BMK/second/a60da4fe",
        "BMK/third/6f3a2760",
        "BMK/fourth/2ed0b8c7"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"路径不存在: {path}")
