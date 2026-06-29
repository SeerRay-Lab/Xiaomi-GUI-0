import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple

# 导入已有的工具函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "小红书搜索\"适合雨天听的歌单\"，找到3首歌，去QQ音乐里把它们都加到我的\"我喜欢\"列表里"
TASK_ID = 11
STEPRULES = """评分规则

1. 打开小红书App，搜索"适合雨天听的歌单"并找到歌单 → 总分:0.25

2. 打开QQ音乐App → 总分:0.5

3. 检测在QQ音乐中搜索了3首歌曲 → 总分:0.7

4. 这3首歌曲是来自小红书的 → 总分:1.0

一票否决条件

未找到"适合雨天听的歌单" → 分数:0

未识别出3首歌曲 → 分数:0"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """加载轨迹数据，同时返回xml_strings, actions和task_data"""
    task_json_path = os.path.join(path, "task.json")
    with open(task_json_path, 'r', encoding='utf-8') as f:
        task_data = json.load(f)

    steps = task_data.get('data', task_data.get('steps', []))
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

    return xml_strings, actions, steps


def extract_all_text_from_xml(xml_string: str) -> str:
    """从XML中提取所有文本"""
    all_text = []
    try:
        root = ET.fromstring(xml_string)
        for elem in root.iter():
            text = elem.get('text', '')
            ocr_texts = elem.get('ocr_texts', '')
            if text:
                all_text.append(text)
            if ocr_texts:
                all_text.append(ocr_texts)
    except Exception as e:
        pass

    return ' '.join(all_text)


def get_xiaohongshu_song_names(xml_strings: List[str]) -> List[str]:
    """从小红书页面中提取歌曲名称"""
    song_names = []

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否是小红书页面
            is_xhs = False
            for elem in root.iter():
                package = elem.get('package', '')
                if 'xhs' in package:
                    is_xhs = True
                    break

            if is_xhs:
                # 从小红书页面提取文本内容
                texts = []
                for elem in root.iter():
                    text = elem.get('text', '')
                    ocr_texts = elem.get('ocr_texts', '')
                    if text and len(text) > 0 and len(text) < 50:  # 歌曲名通常较短
                        texts.append(text)
                    if ocr_texts and len(ocr_texts) > 0 and len(ocr_texts) < 50:
                        texts.append(ocr_texts)

                # 去重
                song_names.extend(texts)
        except Exception as e:
            pass

    # 去重并返回
    return list(set(song_names))


def get_qqmusic_search_keywords(xml_strings: List[str]) -> List[str]:
    """从QQ音乐搜索框中提取搜索关键词"""
    keywords = []

    # 从后向前遍历，查找搜索框中的关键词
    for xml_string in reversed(xml_strings):
        try:
            root = ET.fromstring(xml_string)
            # 检查是否是QQ音乐页面
            is_qqmusic = False
            for elem in root.iter():
                package = elem.get('package', '')
                if 'qqmusic' in package:
                    is_qqmusic = True
                    break

            if is_qqmusic:
                # 在QQ音乐页面中查找搜索框
                for elem in root.iter():
                    text = elem.get('text', '')
                    ocr_texts = elem.get('ocr_texts', '')
                    resource_id = elem.get('resource-id', '')

                    # 如果是搜索框元素
                    if 'search' in resource_id:
                        query_part = text or ocr_texts
                        if query_part and len(query_part) > 0:
                            keywords.append(query_part)
        except Exception as e:
            pass

    return list(set(keywords)) if keywords else []


def count_qqmusic_searches(xml_strings: List[str]) -> int:
    """统计QQ音乐中的搜索操作数量"""
    search_count = 0

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否是QQ音乐页面
            is_qqmusic = False
            for elem in root.iter():
                package = elem.get('package', '')
                if 'qqmusic' in package:
                    is_qqmusic = True
                    break

            if is_qqmusic:
                # 在QQ音乐页面中查找搜索框元素
                for elem in root.iter():
                    resource_id = elem.get('resource-id', '')
                    # 计数搜索框元素的出现
                    if 'search' in resource_id:
                        search_count += 1
        except Exception as e:
            pass

    return search_count


def check_rejection_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    # 一票否决条件1: 未找到"适合雨天听的歌单"
    has_rainy_day_playlist = False

    for xml_string in xml_strings:
        try:
            # 方法1: 同时包含"适合"、"雨天"、"歌单"的元素
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined_text = (text or '') + ' ' + (ocr_texts or '')

                if '适合' in combined_text and '雨天' in combined_text and '歌' in combined_text:
                    has_rainy_day_playlist = True
                    break

            if has_rainy_day_playlist:
                break
        except Exception as e:
            pass

    if not has_rainy_day_playlist:
        return True, "未找到\"适合雨天听的歌单\""

    # 一票否决条件2: 未识别出3首歌曲
    xiaohongshu_songs = get_xiaohongshu_song_names(xml_strings)
    if len(xiaohongshu_songs) < 3:
        return True, f"未识别出3首歌曲（仅识别出{len(xiaohongshu_songs)}首）"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书App，搜索"适合雨天听的歌单"并找到歌单"""
    rule1_xpaths = [
        "//*[contains(@package, 'xhs')]",
        "//*[(contains(@text, '适合') or contains(@ocr_texts, '适合')) and (contains(@text, '雨天') or contains(@ocr_texts, '雨天'))]",
        "//*[(contains(@text, '歌单') or contains(@ocr_texts, '歌单'))]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
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
            except Exception as e:
                pass

    # 至少需要3个条件都满足：小红书App + 适合雨天 + 歌单
    if sum(checked) >= 3:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书并搜索适合雨天听的歌单"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未在小红书搜索适合雨天听的歌单"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开QQ音乐App"""
    rule2_xpaths = [
        "//*[contains(@package, 'qqmusic')]",
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
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
            except Exception as e:
                pass

    # 至少需要检测到QQ音乐App
    if any(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开QQ音乐App"

    return False, "未打开QQ音乐App"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：检测在QQ音乐中搜索了3首歌曲"""
    # 统计QQ音乐中的搜索操作数量
    search_operations = []
    search_texts=[]

    for i, xml_string in enumerate(xml_strings):
        try:
            root = ET.fromstring(xml_string)
            is_qqmusic = False
            for elem in root.iter():
                package = elem.get('package', '')
                if 'qqmusic' in package:
                    is_qqmusic = True
                    break

            if is_qqmusic:
                # 检查搜索框中是否有内容
                for elem in root.iter():
                    resource_id = elem.get('resource-id', '')
                    text = elem.get('text', '')
                    ocr_texts = elem.get('ocr_texts', '')

                    if 'search' in resource_id and len(text)>1:
                        #search_operations.append(i)
                        search_texts.append(text)
        except Exception as e:
            pass

    # 需要至少3次搜索操作
    unique_search_steps = list(set(search_texts))
    if len(unique_search_steps) >= 3:
        return True, f"步骤{sorted(unique_search_steps)}: 在QQ音乐中进行了{len(unique_search_steps)}次搜索"

    if len(unique_search_steps) > 0:
        return False, f"仅在QQ音乐中进行了{len(unique_search_steps)}次搜索（需要3次）"

    return False, "未在QQ音乐中进行搜索"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：这3首歌曲是来自小红书的"""
    # 步骤1: 从QQ音乐搜索框中提取搜索过的歌曲名
    qqmusic_song_names = []

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否是QQ音乐页面，并从搜索框中提取歌曲名
            for elem in root.iter():
                package = elem.get('package', '')
                resource_id = elem.get('resource-id', '')
                text = elem.get('text', '')

                # 限定在QQ音乐的搜索框中（resource-id包含'search'）
                if 'qqmusic' in package and 'search' in resource_id and text and len(text) > 1:
                    qqmusic_song_names.append(text)
        except Exception as e:
            pass

    # 去重
    qqmusic_song_names = list(set(qqmusic_song_names))

    if len(qqmusic_song_names) < 3:
        return False, f"未从QQ音乐找到3首歌曲（仅找到{len(qqmusic_song_names)}首）"

    print("qqmusic_song_names",qqmusic_song_names)
    # 步骤2: 从小红书页面中收集所有text和ocr_texts，用于验证
    xiaohongshu_all_texts = []

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否是小红书页面
            is_xhs = False
            for elem in root.iter():
                package = elem.get('package', '')
                if 'xhs' in package:
                    is_xhs = True
                    break

            if is_xhs:
                # 从小红书页面提取所有文本
                for elem in root.iter():
                    text = elem.get('text', '')
                    ocr_texts = elem.get('ocr_texts', '')

                    if text:
                        xiaohongshu_all_texts.append(text)
                    if ocr_texts:
                        xiaohongshu_all_texts.append(ocr_texts)
        except Exception as e:
            pass

    if not xiaohongshu_all_texts:
        return False, "未找到小红书页面数据"

    # 步骤3: 检查QQ音乐中的歌曲名是否在小红书页面中出现
    xiaohongshu_combined = ' '.join(xiaohongshu_all_texts)
    matched_songs = []

    for song in qqmusic_song_names:
        if song and len(song) > 1:
            # 如果歌曲名包含空格，分割后只要有1个部分匹配就算
            if ' ' in song:
                song_parts = song.split(' ')
                for part in song_parts:
                    if part and len(part) > 1 and part in xiaohongshu_combined:
                        matched_songs.append(song)
                        break
            else:
                # 不含空格，直接检查整个歌曲名是否出现在小红书内容中
                if song in xiaohongshu_combined:
                    matched_songs.append(song)

    # 步骤4: 如果至少3个歌曲名在小红书中都能找到，则规则满足
    if len(matched_songs) >= 3:
        return True, f"验证了QQ音乐中搜索的3首歌曲来自小红书: {','.join(matched_songs[:3])}"

    if len(matched_songs) > 0:
        return False, f"仅验证了{len(matched_songs)}首歌曲来自小红书: {','.join(matched_songs)}，需要3首"

    return False, "未验证任何歌曲来自小红书"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 11,
            "path": "...",
            "steprules": "...",
            "total_score": 1.0,
            "details": [...]
        }
    """
    try:
        xml_strings, actions, task_steps = load_trajectory_data(path)
    except Exception as e:
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
            "rule": "打开小红书App，搜索\"适合雨天听的歌单\"并找到歌单",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "打开QQ音乐App",
            "score": 0.5 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "检测在QQ音乐中搜索了3首歌曲",
            "score": 1.0 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "这3首歌曲是来自小红书的",
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
        "BMK/first/f088a08f",
        "BMK/2026-04-29/小红书_qq音乐/BMK评测/a5219795-8ed3-41d1-aec8-7046a6d46b95",
        "BMK/second/495e9e54",
        "BMK/third/f4805c4d",
        "BMK/fourth/55a0a405"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
