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
QUERY = "今晚要请几个回族的朋友来家里吃饭，去盒马帮我挑三种不同类型的肉，加入购物车"
TASK_ID = 10
STEPRULES = """1. 打开盒马，搜索肉类商品 → 分数:0.33

2. 挑选三种不同类型的肉（如牛肉、羊肉、鸡肉等清真肉类） → 分数:0.33

3. 将选中的肉类加入购物车 → 分数:0.34

一票否决

选择了非清真肉类（如猪肉）→ 分数:0"""


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
    """检查一票否决条件：选择了非清真肉类（如猪肉）"""
    rejection_xpath = "//*[(contains(@text, '猪肉')  or contains(@text, '猪') ) and bbox_contains_point(../@bounds, $point)]"

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        try:
            match_flag, _ = evaluate_action_xml(xml_string, rejection_xpath, action_dict)
            if match_flag == 1:
                print(i)
                return True, "选择了非清真肉类（如猪肉）"
        except:
            pass

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开盒马，搜索肉类商品"""
    rule1_xpaths = [
        "//*[contains(@text, '盒马') or contains(@ocr_texts, '盒马') or contains(@package, 'hema')]",
        "//*[contains(@text, '肉') or contains(@ocr_texts, '肉') or contains(@text, '肉类') or contains(@ocr_texts, '肉类')]",
        "//*[contains(@text, '搜索') or contains(@ocr_texts, '搜索') or contains(@text, '搜') or contains(@ocr_texts, '搜')]"
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

        # 需要打开盒马并搜索肉类
        if checked[0] and (checked[1] or checked[2]):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开盒马搜索肉类"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开盒马或未搜索肉类"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：挑选三种不同类型的肉"""
    rule2_xpaths = [
        "//*[(contains(@text, '牛') )] and //*[(contains(@text, '加入购物车') or contains(@ocr_texts, '加入购物车') or contains(@content-desc, '加入购物车')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '羊'))] and //*[(contains(@text, '加入购物车') or contains(@ocr_texts, '加入购物车') or contains(@content-desc, '加入购物车')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '鸡') )] and //*[(contains(@text, '加入购物车') or contains(@ocr_texts, '加入购物车') or contains(@content-desc, '加入购物车')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '鸭') )] and //*[(contains(@text, '加入购物车') or contains(@ocr_texts, '加入购物车') or contains(@content-desc, '加入购物车')) and bbox_contains_point(@bounds, $point)]",
        "//*[(contains(@text, '鱼') or contains(@text, '海鲜') )] and //*[(contains(@text, '加入购物车') or contains(@ocr_texts, '加入购物车') or contains(@content-desc, '加入购物车')) and bbox_contains_point(@bounds, $point)]"
    ]
    #//*[(contains(@text, '鸭') ) and bbox_contains_point(../@bounds, $point)]

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

        # 需要至少找到三种不同类型的肉
        if sum(checked) >= 3:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 挑选三种不同类型的肉"

    if any(checked):
        return False, f"只找到{sum(checked)}种肉类，需要3种"

    return False, "未找到足够的肉类选择"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：将肉类加入购物车"""
    rule3_xpaths = [
        "//*[(contains(@text, '加入购物车') or contains(@ocr_texts, '加入购物车') or contains(@content-desc, '加入购物车')) and bbox_contains_point(@bounds, $point)]"
    ]

    evidence_steps = []

    # 从新到旧遍历，查找加入购物车的操作
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx in range(len(rule3_xpaths) - 1, -1, -1):
            xpath = rule3_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    evidence_steps.append(i)
                    return True, f"步骤{i}: 将肉类加入购物车"
            except:
                pass

    return False, "未将肉类加入购物车"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 10,
            "path": "BMK/...",
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

    details = [
        {
            "rule": "打开盒马，搜索肉类商品",
            "score": 0.33 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "挑选三种不同类型的肉（如牛肉、羊肉、鸡肉等清真肉类）",
            "score": 0.33 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "将选中的肉类加入购物车",
            "score": 0.34 if rule3_satisfied else 0.0,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
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
        "BMK/first/03faf846",
        "BMK/second/4c0f6834",
        "BMK/third/62c7b5dd",
        "BMK/fourth/9df76d3d"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
