import json                         
import os
import sys                                                                                                                                          
import re
from typing import Dict, List, Any, Tuple, Optional                                                                                                 
                                                        
# 导入已有的工具函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "去QQ音乐搜林俊杰的热门歌单，播放第一首，然后去B站播放这首歌的演唱会现场版视频"
TASK_ID = 8
STEPRULES = """评分规则

打开QQ音乐App，搜索"林俊杰"并找到热门歌单 → 总分:0.25

进入热门歌单，播放第一首歌曲 → 总分:0.5

打开B站App，搜索歌曲名+"演唱会现场版"，验证搜索内容与播放歌曲相符 → 总分:0.75

在搜索结果中找到对应的演唱会现场版视频并播放 → 总分:1.0

一票否决

未完成从QQ音乐到B站的切换 → 总分:0

在B站搜索的不是QQ音乐中播放的那首歌 → 总分:0

播放的不是演唱会现场版视频 → 总分:0"""


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


def extract_text_from_search_query(xml_strings: List[str]) -> Optional[str]:
    """从B站搜索页面提取搜索关键词（"演唱会现场版"之前的文字）"""
    import xml.etree.ElementTree as ET

    # 从后向前遍历，找搜索框或搜索结果中包含"演唱会现场版"的关键词
    for xml_string in reversed(xml_strings):
        try:
            root = ET.fromstring(xml_string)
            all_texts = []
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                if text:
                    all_texts.append(text)
                if ocr_texts:
                    all_texts.append(ocr_texts)
            
            #print("all_texts",all_texts)
            # 寻找包含"演唱会现场版"的文本
            for text in all_texts:
                if '演唱会现场版' in text or '演唱会' in text and '现场版' in text:
                    #print("here",text)
                    # 提取"演唱会现场版"前的部分（即歌曲名）
                    if '演唱会现场版' in text:
                        query_part = text.split('演唱会现场版')[0].strip()
                    elif '演唱会' in text:
                        query_part = text.split('演唱会')[0].strip()
                    else:
                        query_part = text
                    if query_part and len(query_part) > 0:
                        return query_part
        except:
            pass

    # 从后向前遍历，找搜索框或搜索结果中包含"演唱会现场版"的关键词
    for xml_string in reversed(xml_strings):
        try:
            root = ET.fromstring(xml_string)
            all_texts = []
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                if '演唱会' in text or  '演唱会' in ocr_texts:
                    resource_id= elem.get('resource-id', '')
                    if 'search' in resource_id:
                        query_part = text.split('演唱会')[0].strip()

                        if query_part and len(query_part) > 0:
                            return query_part
                if '现场版' in text or  '现场版' in ocr_texts:
                    resource_id= elem.get('resource-id', '')
                    if 'search' in resource_id:
                        query_part = text.split('现场版')[0].strip()

                        if query_part and len(query_part) > 0:
                            return query_part
        except:
            pass
    return None


def check_rejection_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    has_qqmusic = False
    has_bilibili = False

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]

        # 检查是否有QQ音乐
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'qqmusic') or contains(@text, 'QQ音乐') or contains(@ocr_texts, 'QQ音乐')]", action_dict)
            if match_flag == 1:
                has_qqmusic = True
        except:
            pass

        # 检查是否有B站
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'bili') or contains(@text, 'B站') or contains(@ocr_texts, 'B站') or contains(@text, '哔哩哔哩')]", action_dict)
            if match_flag == 1:
                has_bilibili = True
        except:
            pass

    if not (has_qqmusic and has_bilibili):
        return True, "未完成从QQ音乐到B站的切换"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开QQ音乐App，搜索"林俊杰"并找到热门歌单"""
    rule1_xpaths = [
        "//*[contains(@package, 'qqmusic') or contains(@text, 'QQ音乐') or contains(@ocr_texts, 'QQ音乐')]",
        "//*[contains(@text, '林俊杰') or contains(@ocr_texts, '林俊杰')]",
        "//*[contains(@text, '热门') or contains(@ocr_texts, '热门')]",
        "//*[contains(@text, '歌单') or contains(@ocr_texts, '歌单')]"
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

        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开QQ音乐搜索林俊杰并找到热门歌单"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未找到热门歌单"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：进入热门歌单，播放第一首歌曲"""
    rule2_xpaths = [
        "//*[contains(@text, '林俊杰')] and //*[contains(@content-desc, '暂停')] and //*[contains(@content-desc, '下一曲')]",
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

        if checked[0]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 播放第一首歌曲"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未播放歌曲"


def check_text_in_playback_page(playback_xml: str, search_text: str) -> bool:
    """检查搜索关键词是否出现在播放页面中"""
    import xml.etree.ElementTree as ET

    if not search_text or not playback_xml:
        return False

    try:
        root = ET.fromstring(playback_xml)
        for elem in root.iter():
            text = elem.get('text', '')
            ocr_texts = elem.get('ocr_texts', '')

            # 检查是否包含搜索关键词的任何部分
            if search_text in text or search_text in ocr_texts:
                return True

            # 也检查关键词的每个字
            for char in search_text:
                if char in text or char in ocr_texts:
                    return True
    except:
        pass

    return False


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开B站App，搜索歌曲名+"演唱会现场版"，验证搜索内容与播放歌曲相符"""
    # 先检查B站是否打开
    b_station_found = False
    for xml_string in xml_strings:
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'bili') or contains(@text, 'B站') or contains(@ocr_texts, 'B站')]", action_dict)
            if match_flag == 1:
                b_station_found = True
                break
        except:
            pass

    if not b_station_found:
        return False, "未找到B站应用"

    # 提取搜索关键词（"演唱会现场版"前的内容）
    search_query = extract_text_from_search_query(xml_strings)
    print("len",len(xml_strings))
    print(search_query)
    if not search_query:
        return False, "无法从B站搜索页面提取歌曲名"

    # 检查这些关键词是否在播放页面出现过（第1-2步之间）
    playback_xml_idx = -1
    for i, xml_string in enumerate(xml_strings):
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'qqmusic') or contains(@text, 'QQ音乐') or contains(@ocr_texts, 'QQ音乐')]", action_dict)
            if match_flag == 1:
                playback_xml_idx = i
        except:
            pass

    if playback_xml_idx >= 0:
        playback_xml = xml_strings[playback_xml_idx]
        if check_text_in_playback_page(playback_xml, search_query):
            return True, f"验证成功: 搜索关键词'{search_query}'出现在播放页面中"
        else:
            return False, f"验证失败: 搜索关键词'{search_query}'未在播放页面找到"

    return False, "无法验证播放页面"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：在搜索结果中找到对应的演唱会现场版视频并播放"""
    rule4_xpaths = [
        "//*[contains(@text, '演唱会') or contains(@ocr_texts, '演唱会')]",
        "//*[contains(@text, '林俊杰') or contains(@ocr_texts, '林俊杰')]",
        "//*[contains(@text, '现场版') or contains(@ocr_texts, '现场版')]"
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 播放演唱会现场版视频"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未播放演唱会现场版视频"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 8,
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
            "rule": "打开QQ音乐App，搜索\"林俊杰\"并找到热门歌单",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "进入热门歌单，播放第一首歌曲",
            "score": 0.25 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "打开B站App，搜索歌曲名+\"演唱会现场版\"，验证搜索内容与播放歌曲相符",
            "score": 0.25 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "在搜索结果中找到对应的演唱会现场版视频并播放",
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
        "BMK/first/fe31166b",
        "BMK/2026-04-29/qq音乐_b站/BMK评测/39dc812c-d3ca-4d6e-b17d-d3fdc0609b05",
        "BMK/second/4bd83580",
        "BMK/third/d8813ce2",
        "BMK/fourth/d4e476ee"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))