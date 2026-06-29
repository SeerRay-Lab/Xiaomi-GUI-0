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
QUERY = "我要上小红书发一篇帖子，内容是关于广州的3天旅游感受，你帮我上小红书看一看别人的帖子，挑5个点赞量最高的总结一下。要求文案自然流畅，配图在帖子里找两张，然后直接给我发出去就行"
TASK_ID = 9
STEPRULES = """评分规则

打开小红书App → 总分:0.15（单独0.15）

搜索"广州 3天旅游"或"广州旅游攻略"等相关关键词，浏览帖子 → 总分:0.3（单独0.15）

找出5个点赞量最高的帖子（需要识别点赞数），并总结内容要点 → 总分:0.6（单独0.3）

从浏览过的帖子中选择2张配图，添加到帖子里，识别到点击下一步按钮 → 总分:0.8（单独0.2）

发布帖子，识别到点击发布按钮 → 总分:1.0（单独0.2）

一票否决

未完成帖子发布 → 总分:0

帖子内容与广州旅游无关 → 总分:0

配图不是从帖子中找的（如用了不相关图片） → 总分:0"""


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


def extract_like_count(text: str) -> Optional[int]:
    """从文本中提取点赞数"""
    # 处理 "999" 或 "9.9万" 或 "9.9K" 的格式
    if not text:
        return None

    try:
        # 移除所有非数字和关键字符
        cleaned = re.sub(r'[^0-9\.,万K]', '', text)

        if '万' in text or 'K' in text:
            # 处理"9.9万"的格式
            match = re.search(r'(\d+\.?\d*)\s*万', text)
            if match:
                return int(float(match.group(1)) * 10000)
            match = re.search(r'(\d+\.?\d*)\s*K', text)
            if match:
                return int(float(match.group(1)) * 1000)
        else:
            # 处理直接数字
            match = re.search(r'(\d+)', text)
            if match:
                return int(match.group(1))
    except:
        pass

    return None


def extract_top_5_posts_info(xml_strings: List[str]) -> Optional[str]:
    """从轨迹中提取点赞最高的5个帖子信息"""
    import xml.etree.ElementTree as ET

    posts_with_likes = []

    # 遍历所有页面，查找包含点赞数的帖子
    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')

                # 查找包含"赞"或"点赞"的文本
                full_text = text + ' ' + ocr_texts
                if '赞' in full_text or '点赞' in full_text:
                    like_count = extract_like_count(full_text)
                    if like_count is not None and like_count > 0:
                        posts_with_likes.append({
                            'text': text or ocr_texts,
                            'likes': like_count
                        })
        except:
            pass

    if posts_with_likes:
        # 按点赞数排序，取前5个
        posts_with_likes.sort(key=lambda x: x['likes'], reverse=True)
        top_5 = posts_with_likes[:5]
        return f"找到{len(top_5)}个高赞帖子，最高赞数: {top_5[0]['likes']}"

    return None


def check_rejection_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    has_xiaohongshu = False
    has_publish = False
    has_guangzhou_content = False

    for xml_string in xml_strings:
        try:
            action_dict = {"action": "click", "params": {"position": [0, 0]}}

            # 检查小红书应用
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@package, 'xhs') or contains(@text, '小红书') or contains(@ocr_texts, '小红书')]", action_dict)
            if match_flag == 1:
                has_xiaohongshu = True

            # 检查内容中是否包含广州旅游相关内容
            match_flag, _ = evaluate_action_xml(xml_string, "//*[contains(@text, '广州') and (contains(@text, '旅游') or contains(@text, '天') or contains(@text, '攻略'))]", action_dict)
            if match_flag == 1:
                has_guangzhou_content = True
        except:
            pass


    if has_xiaohongshu and not has_guangzhou_content:
        return True, "帖子内容与广州旅游无关"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书App"""
    rule1_xpaths = [
        "//*[contains(@package, 'xhs') or contains(@text, '小红书') or contains(@ocr_texts, '小红书')]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule1_xpaths)):
            xpath = rule1_xpaths[xpath_idx]

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if any(checked):
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 成功打开小红书App"

    return False, "未打开小红书App"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：搜索"广州 3天旅游"或"广州旅游攻略"等相关关键词，浏览帖子"""
    rule2_xpaths = [
        "//*[contains(@text, '搜索') or contains(@ocr_texts, '搜索')]",
        "//*[contains(@text, '广州') and (contains(@text, '旅游') or contains(@text, '攻略') or contains(@text, '3天') or contains(@ocr_texts, '旅游') or contains(@ocr_texts, '攻略') )]",
        "//*[contains(@text, '广州旅游') or contains(@ocr_texts, '广州旅游')]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule2_xpaths)):
            xpath = rule2_xpaths[xpath_idx]

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if sum(checked) >= 2:
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索并浏览广州旅游相关帖子"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未搜索广州旅游内容"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：找出5个点赞量最高的帖子（需要识别点赞数），并总结内容要点"""
    rule3_xpaths = [
        "//*[contains(@text, '点赞') or contains(@ocr_texts, '点赞')]",
        "//*[contains(@text, '赞') or contains(@ocr_texts, '赞')]",
        "//*[(contains(@text, '广州') or contains(@ocr_texts, '广州')) and contains(@text, '攻略')]"
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule3_xpaths)):
            xpath = rule3_xpaths[xpath_idx]

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    # 尝试提取高赞帖子信息
    top_5_info = extract_top_5_posts_info(xml_strings)

    if sum(checked) >= 2:
        evidence = f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 识别点赞数据"
        if top_5_info:
            evidence += f" ({top_5_info})"
        return True, evidence

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未找到点赞最高的帖子"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：从浏览过的帖子中选择2张配图，添加到帖子里，识别到点击下一步按钮"""
    rule4_xpaths = [
        "//*[contains(@text, '添加图片') or contains(@ocr_texts, '添加图片') or contains(@text, '从相册选择') or contains(@ocr_texts, '从相册选择')]",
        "//*[(contains(@text, '下一步') or contains(@ocr_texts, '下一步')) and bbox_contains_point(@bounds, $point)]"
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule4_xpaths)):
            xpath = rule4_xpaths[xpath_idx]

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if sum(checked) >= 2:
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 添加配图并点击下一步"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未添加配图或未点击下一步"


def evaluate_rule_5(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则5：发布帖子，识别到点击发布按钮"""
    rule5_xpaths = [
        "//*[contains(@package, 'xhs') and contains(@text, '发布笔记') and bbox_contains_point(@bounds, $point) ]"
    ]

    checked = [False] * len(rule5_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule5_xpaths)):
            xpath = rule5_xpaths[xpath_idx]

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
            except:
                pass

    if any(checked):
        return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 发布帖子成功"

    return False, "未发布帖子"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 9,
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
    rule5_satisfied, rule5_evidence = evaluate_rule_5(xml_strings, actions)

    details = [
        {
            "rule": "打开小红书App",
            "score": 0.15 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "搜索\"广州 3天旅游\"或\"广州旅游攻略\"等相关关键词，浏览帖子",
            "score": 0.15 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "找出5个点赞量最高的帖子（需要识别点赞数），并总结内容要点",
            "score": 0.3 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "从浏览过的帖子中选择2张配图，添加到帖子里，识别到点击下一步按钮",
            "score": 0.2 if rule4_satisfied else 0.0,
            "satisfied": rule4_satisfied,
            "evidence": rule4_evidence
        },
        {
            "rule": "发布帖子，识别到点击发布按钮",
            "score": 0.2 if rule5_satisfied else 0.0,
            "satisfied": rule5_satisfied,
            "evidence": rule5_evidence
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
        "BMK/first/72d29efc",
        "BMK/2026-04-29/小红书/BMK评测/f0c9e141-407f-4ab0-bc8d-7b750fa886d0",
        "BMK/second/66c2989a",
        "BMK/third/d020457f",
        "BMK/fourth/4d7cc8cc"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
