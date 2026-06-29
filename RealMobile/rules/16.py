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


QUERY = "看一下微博雷军最近宣发的产品，帮我在抖音上搜一下这个产品热度最高的内容，看看评论区的五条评价，然后发个微博说一下用户对产品的看法"
TASK_ID = 16
STEPRULES = """评分规则（分阶段验证进度）

1. 打开微博，查看雷军宣发的产品 → 总分:0.25

2. 打开抖音，搜索该产品，找到热度最高的内容 → 总分:0.5

3. 查看评论区的评价（识别到至少1条评论） → 总分:0.75

4. 发布微博，说用户对产品的看法 → 总分:1.0

一票否决条件：
- 未找到雷军宣发的产品 → 分数:0
- 未在抖音上搜索或未找到内容 → 分数:0

规则特点：
- 支持多XPath匹配，一个页面可匹配多条xpath
- 不使用break，使用布尔列表完整检查
- 完整的错误处理和异常捕捉
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
    # 一票否决条件1: 未找到雷军宣发的产品
    has_weibo = False
    has_leijun = False
    has_product = False

    # 一票否决条件2: 未在抖音上搜索或未找到内容
    has_douyin = False
    has_search = False

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)

            # 检查是否打开了微博(package包含'weibo'或'sina')
            for elem in root.iter():
                package = elem.get('package', '')
                if 'weibo' in package or 'sina' in package:
                    has_weibo = True

                # 检查是否打开了抖音(package包含'douyin'或'aweme')
                if 'douyin' in package or 'aweme' in package or 'tiktok' in package:
                    has_douyin = True

            # 检查是否包含雷军和产品相关关键词
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查雷军相关关键词
                if '雷军' in combined or '雷布斯' in combined or '小米' in combined:
                    has_leijun = True

                # 检查产品相关关键词（通用产品词）
                if ('产品' in combined or '手机' in combined or '平板' in combined or
                    '电脑' in combined or '新品' in combined or '推荐' in combined or
                    '发布' in combined or '发布会' in combined or '代言' in combined or
                    '宣发' in combined or 'Pro' in combined or 'Max' in combined or
                    'Ultra' in combined or '性能' in combined):
                    has_product = True

                # 检查搜索框或搜索操作
                if ('搜索' in combined or '搜一下' in combined or '搜索框' in combined or
                    'search' in combined.lower() or '查一下' in combined):
                    has_search = True

        except Exception as e:
            pass

    # 检查否决条件1：未找到雷军宣发的产品
    if not (has_weibo and has_leijun and has_product):
        reason = "未找到雷军宣发的产品"
        if not has_weibo:
            reason += "（未打开微博）"
        if not has_leijun:
            reason += "（未识别到雷军相关内容）"
        if not has_product:
            reason += "（未识别到产品相关内容）"
        return True, reason

    # 检查否决条件2：未在抖音上搜索或未找到内容
    if not (has_douyin and has_search):
        reason = "未在抖音上搜索相关内容"
        if not has_douyin:
            reason += "（未打开抖音）"
        if not has_search:
            reason += "（未进行搜索操作）"
        return True, reason

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开微博，查看雷军宣发的产品"""
    rule1_xpaths = [
        "//*[contains(@package, 'weibo') or contains(@package, 'sina')]",
        "//*[(contains(@text, '雷军') or contains(@ocr_texts, '雷军'))]",
        "//*[(contains(@text, '小米') or contains(@ocr_texts, '小米') or contains(@text, '小米集团') or contains(@ocr_texts, '小米集团'))]",
        "//*[(contains(@text, '产品') or contains(@ocr_texts, '产品') or contains(@text, '新品') or contains(@ocr_texts, '新品'))]",
        "//*[(contains(@text, '发布') or contains(@ocr_texts, '发布') or contains(@text, '宣发') or contains(@ocr_texts, '宣发'))]"
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

    # 需要满足：打开微博 + 雷军/小米 + 产品 + 发布
    if sum(checked) >= 4:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开微博查看雷军宣发的产品"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开微博或未查看雷军宣发的产品"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开抖音，搜索该产品，找到热度最高的内容"""
    # 分支规则1: 检查抖音打开和搜索
    branch1_xpaths = [
        "//*[contains(@package, 'douyin') or contains(@package, 'aweme') or contains(@package, 'tiktok')]",
        "//*[(contains(@text, '搜索') or contains(@ocr_texts, '搜索') or contains(@text, '搜索框') or contains(@ocr_texts, '搜索框'))]",
        "//*[(contains(@text, '搜一下') or contains(@ocr_texts, '搜一下') or contains(@text, '查一下') or contains(@ocr_texts, '查一下'))]"
    ]

    # 分支规则2: 检查热度相关关键词或内容列表
    branch2_xpaths = [
        "//*[(contains(@text, '热') or contains(@ocr_texts, '热') or contains(@text, '热度') or contains(@ocr_texts, '热度'))]",
        "//*[(contains(@text, '最热') or contains(@ocr_texts, '最热') or contains(@text, '热门') or contains(@ocr_texts, '热门'))]",
        "//*[(contains(@text, '热搜') or contains(@ocr_texts, '热搜') or contains(@text, '热榜') or contains(@ocr_texts, '热榜'))]",
        "//*[(contains(@text, '点赞') or contains(@ocr_texts, '点赞') or contains(@text, '播放') or contains(@ocr_texts, '播放'))]"
    ]

    checked_branch1 = [False] * len(branch1_xpaths)
    checked_branch2 = [False] * len(branch2_xpaths)
    evidence_steps = []
    keywords_found = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查分支1的xpath匹配（打开抖音和搜索）
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
                        keywords_found.append('抖音打开')
                    elif xpath_idx in [1, 2]:
                        keywords_found.append('搜索框')
            except Exception as e:
                pass

        # 检查分支2的xpath匹配（热度相关内容）
        for xpath_idx in range(len(branch2_xpaths)):
            if checked_branch2[xpath_idx]:
                continue

            xpath = branch2_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked_branch2[xpath_idx] = True
                    evidence_steps.append(i)
                    if xpath_idx in [0, 1, 2]:
                        keywords_found.append('热度相关')
                    elif xpath_idx == 3:
                        keywords_found.append('互动指标')
            except Exception as e:
                pass

        # 分支规则3: 从页面文本内容中提取搜索和内容相关信息
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                resource_id = elem.get('resource-id', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否是搜索结果页面（通常包含列表项、卡片、feed等）
                if (resource_id and ('item' in resource_id or 'card' in resource_id or
                    'feed' in resource_id or 'list' in resource_id or 'video' in resource_id)) or \
                   ((text and len(text) > 10) or (ocr_texts and len(ocr_texts) > 10)):
                    # 检查是否包含热度或互动相关关键词
                    if any(kw in combined for kw in ['热', '热度', '最热', '热门', '热搜', '点赞', '播放', '万']):
                        if '搜索结果' not in keywords_found:
                            keywords_found.append('搜索结果')
                            evidence_steps.append(i)
        except Exception as e:
            pass

    # 满足条件：需要打开抖音 + 搜索操作 + 找到热度相关内容
    has_douyin_open = any(kw in keywords_found for kw in ['抖音打开'])
    has_search_box = any(kw in keywords_found for kw in ['搜索框'])
    has_content = any(kw in keywords_found for kw in ['热度相关', '互动指标', '搜索结果'])

    if has_douyin_open and has_search_box and has_content:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开抖音搜索产品找到热度最高内容（{','.join(set(keywords_found))}）"

    if has_douyin_open or has_search_box:
        return False, f"部分条件满足: {','.join(set(keywords_found))}"

    return False, "未在抖音上搜索或未找到内容"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：查看评论区的评价（识别到至少1条评论）"""
    # 评论相关关键词
    comment_keywords = ['评论', '赞', '点赞', '评价', '回复', '留言', '评论区', '评论列表', 'comment', 'reply']

    rule3_xpaths = [
        "//*[(contains(@text, '评论') or contains(@ocr_texts, '评论'))]",
        "//*[(contains(@text, '赞') or contains(@ocr_texts, '赞') or contains(@text, '点赞') or contains(@ocr_texts, '点赞'))]",
        "//*[(contains(@text, '评价') or contains(@ocr_texts, '评价'))]",
        "//*[(contains(@text, '回复') or contains(@ocr_texts, '回复') or contains(@text, '留言') or contains(@ocr_texts, '留言'))]",
        "//*[(contains(@text, '评论区') or contains(@ocr_texts, '评论区'))]"
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []
    comment_count = 0

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

        # 从页面文本内容中计算评论数量
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                resource_id = elem.get('resource-id', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否是评论项（通常包含较长文本、名字、时间、点赞等）
                if (resource_id and ('comment' in resource_id or 'reply' in resource_id)) or \
                   ((text and len(text) > 5) or (ocr_texts and len(ocr_texts) > 5)):
                    # 检查是否包含评论相关关键词
                    for keyword in comment_keywords:
                        if keyword in combined:
                            comment_count += 1
                            break
        except Exception as e:
            pass

    # 至少需要识别到1条或以上的评论
    if any(checked) or comment_count >= 1:
        count_str = f"{max(comment_count, sum(checked))}"
        return True, f"步骤{sorted(set(evidence_steps))}: 查看评论区评价（识别到至少{count_str}条）"

    return False, "未查看评论区或未识别到评论"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：发布微博，说用户对产品的看法"""
    rule4_xpaths = [
        "//*[contains(@text, '小米') and contains(@class, 'EditText')] ",
        "//*[(contains(@text, '发送') and contains(@package, 'weibo') ) and bbox_contains_point(@bounds, $point)]",
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(rule4_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = rule4_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 选择骑行路线方式"
    
    if all(checked):
        return False, f"部分条件满足: {','.join(set(evidence_steps))}"

    return False, "未发布微博或未包含产品看法相关内容"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 16,
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
            "rule": "1. 打开微博，查看雷军宣发的产品",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 打开抖音，搜索该产品，找到热度最高的内容",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 查看评论区的评价（识别到至少1条评论）",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 发布微博，说用户对产品的看法",
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
        "BMK/first/070dca4f",
        "BMK/second/b497921a",
        "BMK/third/fc9c97e9",
        "BMK/fourth/c65affc3"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
