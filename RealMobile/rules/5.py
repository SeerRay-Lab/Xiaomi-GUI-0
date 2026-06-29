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
QUERY = "给我开通qq音乐年会员"
TASK_ID = 5
STEPRULES = """评分规则

打开QQ音乐App，进入会员中心/我的VIP页面 → 总分:0.5

定位并选择"年费会员/年度会员"套餐（需明确年费套餐，如12个月） → 总分:1.0
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
    rejection_xpaths = [
        # 未经确认直接支付
        "//*[(contains(@text, '支付') or contains(@ocr_texts, '支付')) and not(contains(@text, '确认') or contains(@ocr_texts, '确认')) and bbox_contains_point(@bounds, $point)]",


    ]

    rejection_reasons = [
        "未经用户确认直接完成支付",
    ]

    # 遍历所有步骤检查否决条件
    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        for xpath_idx, xpath in enumerate(rejection_xpaths):
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    return True, rejection_reasons[xpath_idx]
            except:
                pass

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开QQ音乐App，进入会员中心/我的VIP页面"""
    rule1_xpaths = [
        "//*[contains(@package, 'qqmusic') or contains(@text, 'QQ音乐') or contains(@ocr_texts, 'QQ音乐')]",
        "//*[contains(@text, '会员中心') or contains(@ocr_texts, '会员中心') or contains(@text, '我的VIP') or contains(@ocr_texts, '我的VIP') or contains(@text, 'VIP中心') or contains(@ocr_texts, 'VIP中心')]",
        "//*[contains(@text, '我的') or contains(@ocr_texts, '我的')]",
        "//*[contains(@text, 'VIP') or contains(@ocr_texts, 'VIP') or contains(@text, '会员') or contains(@ocr_texts, '会员')]"
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
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开QQ音乐并进入VIP页面"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开QQ音乐或未进入VIP页面"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：定位并选择"年费会员/年度会员"套餐"""
    rule2_xpaths = [
        "//*[(contains(@text, '12个月') or contains(@ocr_texts, '12个月') or contains(@text, '12月') or contains(@ocr_texts, '12月')) and bbox_contains_point(../@bounds, $point)]",
        "//*[(contains(@text, '年费') or contains(@ocr_texts, '年费') or contains(@text, '年度') or contains(@ocr_texts, '年度') or contains(@text, '包年') or contains(@ocr_texts, '包年')) and bbox_contains_point(../@bounds, $point)]",
        "//*[contains(@ocr_texts, '连续包月') or contains(@ocr_texts, '连续包年')]"
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

        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 定位并选择年费会员套餐"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未选择年费会员套餐"



def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "给我开通qq音乐年会员",
            "id": 5,
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

    # 评估各规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)

    details = [
        {
            "rule": "打开QQ音乐App，进入会员中心/我的VIP页面",
            "score": 0.5 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": '定位并选择"年费会员/年度会员"套餐（需明确年费套餐，如12个月）',
            "score": 0.5 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
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
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/ced87024",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/0f4dcc3f",
        "BMK/first/5cb0e25d",
        "BMK/2026-04-29/qq音乐/BMK评测/403f82e6-42b6-4ca2-8a4a-fc5419077288",
        "BMK/second/03abc42e",
        "BMK/third/c17b0e7e",
        "BMK/fourth/ace6bbdc"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))