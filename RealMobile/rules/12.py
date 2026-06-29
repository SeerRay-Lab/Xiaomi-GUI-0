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
QUERY = "我最近想养一只宠物，我比较喜欢python，帮我在小红书搜索一下，找到两篇相关的内容，总结一下喂养指南发个微博"
TASK_ID = 12
STEPRULES = """评分规则

1. 打开小红书App，搜索"python"和宠物相关内容 → 总分:0.25

2. 找到两篇相关的内容/文章 → 总分:0.5

3. 总结喂养指南（识别到相关文字） → 总分:0.75

4. 打开微博App，发布内容 → 总分:1.0

规则特点：
- 规则2和规则3中可能有分支规则，满足1个分支就给分
- 匹配xpath时不要break，允许一个页面匹配多条xpath

一票否决条件

未搜索"python"和宠物相关内容 → 分数:0

未找到至少两篇相关内容 → 分数:0
"""


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """加载轨迹数据，优先使用 _ocr.xml"""
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

        # 构造 action_dict 格式
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
    # 一票否决条件1: 未搜索"python"和宠物相关内容
    has_python_search = False
    has_pet_search = False
    has_xiaohongshu = False

    pet_keywords = ['宠物', '狗', '猫', '鼠', '兔', '鸟', '鱼', '龟', '喂养', '饲养', '养护']

    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 检查是否是小红书页面
            for elem in root.iter():
                package = elem.get('package', '')
                if 'xhs' in package:
                    has_xiaohongshu = True

            # 检查是否包含python关键词
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                if 'python' in combined.lower():
                    has_python_search = True

                # 检查是否包含宠物相关关键词
                for keyword in pet_keywords:
                    if keyword in combined:
                        has_pet_search = True
                        break
        except Exception as e:
            pass

    if not (has_xiaohongshu and has_python_search and has_pet_search):
        return True, "未搜索\"python\"和宠物相关内容"

    # 一票否决条件2: 未找到至少两篇相关内容
    content_count = 0
    for xml_string in xml_strings:
        try:
            root = ET.fromstring(xml_string)
            # 在小红书页面中计算可能的内容项
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                resource_id = elem.get('resource-id', '')

                # 检查是否是内容卡片或列表项
                if (resource_id and ('item' in resource_id or 'card' in resource_id)) or \
                   ((text and len(text) > 10) or (ocr_texts and len(ocr_texts) > 10)):
                    # 检查是否包含宠物相关内容
                    for keyword in pet_keywords:
                        if keyword in (text or '') or keyword in (ocr_texts or ''):
                            content_count += 1
                            break
        except Exception as e:
            pass

    if content_count < 2:
        return True, f"未找到至少两篇相关内容（仅找到{max(0, content_count)}篇）"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开小红书App，搜索"python"和宠物相关内容"""
    rule1_xpaths = [
        "//*[contains(@package, 'xhs')]",
        "//*[(contains(@text, 'python') or contains(@ocr_texts, 'python'))]",
        "//*[(contains(@text, '宠物') or contains(@ocr_texts, '宠物') or contains(@text, '狗') or contains(@ocr_texts, '狗') or contains(@text, '猫') or contains(@ocr_texts, '猫'))]"
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

    # 需要打开小红书、搜索python、搜索宠物相关内容
    if checked[0] and checked[1] and checked[2]:
        return True, f"步骤{sorted(set(evidence_steps))}: 打开小红书搜索python和宠物相关内容"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开小红书或未搜索python和宠物相关内容"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：找到两篇相关的内容/文章（分支规则）"""
    # 方法1: 通过xpath匹配内容卡片
    branch1_xpaths = [
        "//*[(contains(@text, '宠物') or contains(@ocr_texts, '宠物')) and (contains(@text, '喂养') or contains(@ocr_texts, '喂养') or contains(@text, '饲养') or contains(@ocr_texts, '饲养'))]",
        "//*[(contains(@text, '养') or contains(@ocr_texts, '养')) and (contains(@text, '宠物') or contains(@ocr_texts, '宠物'))]"
    ]

    checked = [False] * len(branch1_xpaths)
    evidence_steps = []
    content_found = 0

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查xpath匹配（分支规则1）
        for xpath_idx in range(len(branch1_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = branch1_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    content_found += 1
            except Exception as e:
                pass

        # 检查是否存在多个内容项（分支规则2）
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                resource_id = elem.get('resource-id', '')

                # 检查是否是内容卡片或列表项
                if (resource_id and ('item' in resource_id or 'card' in resource_id)) or \
                   ((text and len(text) > 20) or (ocr_texts and len(ocr_texts) > 20)):
                    combined = (text or '') + ' ' + (ocr_texts or '')
                    if '宠物' in combined or '喂养' in combined or '饲养' in combined:
                        content_found += 1
        except Exception as e:
            pass

    # 至少需要找到2篇相关内容
    if content_found >= 2:
        return True, f"步骤{sorted(set(evidence_steps))}: 找到{content_found}篇相关内容"

    if content_found > 0:
        return False, f"仅找到{content_found}篇相关内容，需要2篇"

    return False, "未找到相关内容"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：总结喂养指南（识别到相关文字）（分支规则）"""
    # 方法1: 通过xpath直接匹配喂养指南相关文字
    branch1_xpaths = [
        "//*[(contains(@text, '喂养') or contains(@ocr_texts, '喂养') or contains(@text, '饲养') or contains(@ocr_texts, '饲养'))]",
        "//*[(contains(@text, '指南') or contains(@ocr_texts, '指南') or contains(@text, '建议') or contains(@ocr_texts, '建议'))]",
        "//*[(contains(@text, '注意') or contains(@ocr_texts, '注意') or contains(@text, '要点') or contains(@ocr_texts, '要点'))]"
    ]

    # 方法2: 检查搜索框或编辑框中是否包含总结内容
    branch2_xpaths = [
        "//*[(contains(@resource-id, 'search') or contains(@resource-id, 'edit') or contains(@resource-id, 'input')) and (contains(@text, '喂养') or contains(@text, '宠物') or contains(@ocr_texts, '喂养') or contains(@ocr_texts, '宠物'))]"
    ]

    checked_branch1 = [False] * len(branch1_xpaths)
    checked_branch2 = [False] * len(branch2_xpaths)
    evidence_steps = []
    keywords_found = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查分支1的xpath匹配
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
                        keywords_found.append('喂养/饲养')
                    elif xpath_idx == 1:
                        keywords_found.append('指南/建议')
                    elif xpath_idx == 2:
                        keywords_found.append('注意/要点')
            except Exception as e:
                pass

        # 检查分支2的xpath匹配
        for xpath_idx in range(len(branch2_xpaths)):
            if checked_branch2[xpath_idx]:
                continue

            xpath = branch2_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked_branch2[xpath_idx] = True
                    evidence_steps.append(i)
                    keywords_found.append('编辑框内容')
            except Exception as e:
                pass

        # 方法3: 从页面文本内容中提取关键信息
        try:
            root = ET.fromstring(xml_string)
            for elem in root.iter():
                text = elem.get('text', '')
                ocr_texts = elem.get('ocr_texts', '')
                combined = (text or '') + ' ' + (ocr_texts or '')

                # 检查是否包含宠物喂养相关的具体指南内容
                if any(kw in combined for kw in ['喂养', '饲养', '饮食', '营养', '温度', '环境', '疫苗', '清洁']):
                    if any(kw in combined for kw in ['指南', '建议', '方法', '步骤', '注意', '要点']):
                        if '喂养指南' not in keywords_found:
                            keywords_found.append('喂养指南')
                            evidence_steps.append(i)
        except Exception as e:
            pass

    # 满足分支规则之一即可给分
    if any(checked_branch1) or any(checked_branch2) or len(keywords_found) > 1:
        return True, f"步骤{sorted(set(evidence_steps))}: 识别到喂养指南相关内容（{','.join(set(keywords_found))}）"

    if len(keywords_found) > 0:
        return False, f"仅识别到部分相关内容: {','.join(set(keywords_found))}"

    return False, "未识别到喂养指南相关内容"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：打开微博App，发布内容"""
    rule4_xpaths = [
        "//*[contains(@package, 'weibo')  and (contains(@text, '蛇') or contains(@text, '蟒')) and contains(@resource-id, 'edit_view')] and  //*[(contains(@text, '发送') ) and bbox_contains_point(@bounds, $point)] ",
        ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings) - 1, -1, -1):
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
            except Exception as e:
                pass

    # 需要打开微博、发布内容
    if all(checked):
        return True, f"步骤{sorted(set(evidence_steps))}: 打开微博发布内容"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未打开微博或未发布内容"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 12,
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


    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)

    details = [
        {
            "rule": "打开小红书App，搜索\"python\"和宠物相关内容",
            "score": 0.25 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "找到两篇相关的内容/文章",
            "score": 0.5 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "总结喂养指南（识别到相关文字）",
            "score": 0.75 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "打开微博App，发布内容",
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
        "BMK/first/605d4d3c",
        "BMK/2026-04-29/小红书_微博/BMK评测/ba432dd6-0f11-446a-99c3-e0ea15e58157",
        "BMK/second/ea3a046b",
        "BMK/third/4a3b584e",
        "BMK/fourth/5dc030e9"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))