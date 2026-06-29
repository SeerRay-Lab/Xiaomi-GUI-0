import json                       
import os
import sys                                                                                                                                          
from typing import Dict, List, Any, Tuple
                                                                                                                                                    
# 导入已有的工具函数                                                                                                                              
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    # 如果在当前目录找不到，尝试相对导入
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


# 固定的任务信息
QUERY = "请给b站up主小约翰可汗充2块钱的电"
TASK_ID = 2
STEPRULES = '''1. 在B站搜索并进入UP主"小约翰可汗"主页 → 总分:0.33

2. 点击"为TA充电/充电"按钮 → 总分:0.66

3. 在选中￥2的情况下点击为TA充电按钮，完成充电2元的操作 → 总分:1.0'''


def load_trajectory_data(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """加载轨迹数据，优先使用 _ocr.xml"""
    task_json_path = os.path.join(path, "task.json")
    with open(task_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    steps = data.get('data', data.get('steps', []))  # 兼容两种格式
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
        position_temp=step['pixel']
            
        if "orig_position" in step["plan"]:
            position_temp=[int(step['plan']['orig_position'][0]), int(step['plan']['orig_position'][1] ) ]
        elif "position" in step["plan"]:
            position_temp=[int(step['pixel'][0]*step['plan']['position'][0]), int(step['pixel'][1]*step['plan']['position'][1] ) ]
        action_dict = {
            "action": "click",
            "params": {"position": position_temp}
        }
        actions.append(action_dict)

    return xml_strings, actions


def check_rejection_conditions(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查一票否决条件"""
    rejection_xpaths = [
        # 向错误账号充电（充电对象不是小约翰可汗）
        "//*[contains(@text, '充电') and (contains(@text, '成功') or contains(@ocr_texts, '成功')) and not(contains(@text, '小约翰可汗') or contains(@ocr_texts, '小约翰可汗'))]",

        # 金额不是2元（选择了其他金额）
        "//*[contains(@text, '充电') and (contains(@text, '成功') or contains(@ocr_texts, '成功')) and (contains(@text, '5元') or contains(@text, '10元') or contains(@text, '20元') or contains(@text, '50元') or contains(@text, '自定义'))]",

        # 误开启自动续费/自动扣款
        "//*[(contains(@text, '自动续费') or contains(@ocr_texts, '自动续费') or contains(@text, '自动扣款') or contains(@ocr_texts, '自动扣款')) and (@checked='true') and bbox_contains_point(@bounds, $point)]"
    ]

    rejection_reasons = [
        "向非小约翰可汗的账号完成充电",
        "支付金额超过2元",
        "误开启自动续费/自动扣款"
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
    """规则1：在B站搜索并进入UP主"小约翰可汗"主页"""
    rule1_xpaths = [
        "//*[contains(@text, '小约翰可汗') or contains(@ocr_texts, '小约翰可汗')]",
        "//*[contains(@text, '用户') or contains(@ocr_texts, '用户') or contains(@text, 'UP主') or contains(@ocr_texts, 'UP主')]",
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    # 从新到旧遍历历史记录
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        # 匹配XPath
        for xpath_idx in range(len(rule1_xpaths) - 1, -1, -1):
            xpath = rule1_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    break
            except:
                pass

        if all(checked):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索到小约翰可汗并进入主页"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未找到小约翰可汗相关信息"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：点击"为TA充电/充电"按钮"""
    rule2_xpaths = [
        "//*[(contains(@text, '充电') or contains(@ocr_texts, '充电')) and bbox_contains_point(../../@bounds, $point)]",
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    # 从新到旧遍历历史记录
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]

        # 匹配XPath
        for xpath_idx in range(len(rule2_xpaths) - 1, -1, -1):
            xpath = rule2_xpaths[xpath_idx]
            if checked[xpath_idx]:
                continue

            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    evidence_steps.append(i)
                    break
            except:
                pass

        if sum(checked) >= 1:  # 至少满足点击充电、选择2元、显示2元
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 点击充电按钮并选择2元"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未执行充电操作或未选择2元"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：在选中￥2的情况下点击为TA充电按钮，完成充电2元的操作"""
    rule3_xpaths = [
        "//*[contains(@text, '给TA充电¥ 2')  and bbox_contains_point(@bounds, $point)] and //*[contains(@text, '小约翰可汗') ]"
    ]

    # 遍历所有步骤查找确认支付按钮
    for i in range(len(xml_strings) - 1, -1, -1):
        xml_string = xml_strings[i]
        action_dict = actions[i]
        xpath = rule3_xpaths[0]

        try:
            match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
            if match_flag == 1:
                return True, f"步骤{i}: 点击确认支付/立即充电按钮"
        except:
            pass

    return False, "未点击确认支付/立即充电按钮"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "请给b站up主小约翰可汗充2块钱的电",
            "id": 2,
            "path": "BMK/...",
            "steprules": "评分规则...",
            "total_score": 1.0,
            "details": [
                {
                    "rule": "...",
                    "score": 0.33,
                    "satisfied": True,
                    "evidence": "..."
                },
                ...
            ],
            "rejection_reason": None
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
            "rule": '在B站搜索并进入UP主"小约翰可汗"主页',
            "score": 0.33 if rule1_satisfied else 0.0,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": '点击"为TA充电/充电"按钮',
            "score": 0.33 if rule2_satisfied else 0.0,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": '在选中￥2的情况下点击为TA充电按钮，完成充电2元的操作',
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
        "BMK/first/a8144c76",
        "BMK/2026-04-29/b站/BMK评测/e6adaabf-914d-45c3-b1a0-bb2f4488ae06",
        "BMK/second/5b7c65a3",
        "BMK/third/a413665c",
        "BMK/fourth/8864f470"
    ]

    results = []
    for path in paths:
        result = evaluate_trajectory(path=path)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))