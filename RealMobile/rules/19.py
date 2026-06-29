import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "查看雷军在抖音、b站和微博一共有多少粉丝，然后私信发送给雷军的抖音账号"
TASK_ID = 19
STEPRULES = """跨平台粉丝查看和私信任务 - 分阶段验证进度（4阶段）

1. 打开抖音，查看雷军账号的粉丝数 → 总分:0.25

2. 打开B站，查看雷军账号的粉丝数 → 总分:0.5

3. 打开微博，查看雷军账号的粉丝数 → 总分:0.75

4. 私信发送给雷军的抖音账号 → 总分:1.0

一票否决条件：
- 未查看三个平台的粉丝数 → 分数:0
- 未私信雷军 → 分数:0

规则特点：
- 支持多XPath匹配，一个页面可匹配多条xpath
- 使用 [False] * len(xpaths) 布尔列表，不使用break
- 完整的错误处理和异常捕捉
- 支持5个path路径的多路径input"""


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
    """检查一票否决条件：向非雷军账号发送私信（发送时页面中没有出现雷军）"""
    # 检查发送时是否包含雷军名称
    veto_xpaths = [
        "//*[contains(@text, '发送') and bbox_contains_point(@bounds, $point)]"
    ]

    checked = [False] * len(veto_xpaths)

    for i, xml_string in enumerate(xml_strings):
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        for xpath_idx in range(len(veto_xpaths)):
            if checked[xpath_idx]:
                continue

            xpath = veto_xpaths[xpath_idx]
            try:
                match_flag, _ = evaluate_action_xml(xml_string, xpath, action_dict)
                if match_flag == 1:
                    checked[xpath_idx] = True
                    # 发送时检查是否有雷军或雷军账号标识
                    lei_jun_xpaths = [
                        "//*[contains(@text, '雷军')]",
                        "//*[contains(@text, 'leijun')]"
                    ]
                    lei_jun_found = False
                    for lei_jun_xpath in lei_jun_xpaths:
                        try:
                            lei_jun_flag, _ = evaluate_action_xml(xml_string, lei_jun_xpath, {})
                            if lei_jun_flag == 1:
                                lei_jun_found = True
                                break
                        except:
                            pass

                    if not lei_jun_found:
                        return True, "检测到向非雷军账号发送私信"
            except:
                pass

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音，查看雷军账号的粉丝数"""
    rule1_xpaths = [
        # 抖音平台标识
        "//*[ contains(@package, 'aweme')]",
        # 雷军账号标识
        "//*[contains(@text, '雷军')]",
        # 粉丝数关键词和数字
        "//*[contains(@text, '粉丝') and (contains(@text, '万') or contains(@text, '亿') or contains(@text, '0') or contains(@text, '1') or contains(@text, '2') or contains(@text, '3') or contains(@text, '4') or contains(@text, '5') or contains(@text, '6') or contains(@text, '7') or contains(@text, '8') or contains(@text, '9'))]"
    ]

    checked = [False] * len(rule1_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
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
            except:
                pass

        # 需要至少匹配抖音(xpath[0])和粉丝数(xpath[2])，最好还有雷军(xpath[1])
        if checked[0] and checked[2]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 确认抖音粉丝数"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未查看抖音粉丝数"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：打开B站，查看雷军账号的粉丝数"""
    rule2_xpaths = [
        # B站平台标识
        "//*[contains(@package, 'bili') ]",
        # 雷军账号标识
        "//*[contains(@text, '雷军')]",
        # 粉丝数关键词和数字
        "//*[contains(@text, '粉丝') and (contains(@text, '万') or contains(@text, '亿') or contains(@text, '0') or contains(@text, '1') or contains(@text, '2') or contains(@text, '3') or contains(@text, '4') or contains(@text, '5') or contains(@text, '6') or contains(@text, '7') or contains(@text, '8') or contains(@text, '9'))]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
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
            except:
                pass

        # 需要至少匹配B站(xpath[0])和粉丝数(xpath[2])，最好还有雷军(xpath[1])
        if checked[0] and checked[2]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 确认B站粉丝数"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未查看B站粉丝数"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：打开微博，查看雷军账号的粉丝数"""
    rule3_xpaths = [
        # 微博平台标识
        "//*[contains(@package, 'weibo') ]",
        # 雷军账号标识
        "//*[contains(@text, '雷军')]",
        # 粉丝数关键词和数字
        "//*[contains(@text, '粉丝') and (contains(@text, '万') or contains(@text, '亿') or contains(@text, '0') or contains(@text, '1') or contains(@text, '2') or contains(@text, '3') or contains(@text, '4') or contains(@text, '5') or contains(@text, '6') or contains(@text, '7') or contains(@text, '8') or contains(@text, '9'))]"
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

        # 需要至少匹配微博(xpath[0])和粉丝数(xpath[2])，最好还有雷军(xpath[1])
        if checked[0] and checked[2]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 确认微博粉丝数"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未查看微博粉丝数"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：私信发送给雷军的抖音账号"""
    rule4_xpaths = [
        # 私信操作
        "//*[contains(@text, '私信') or contains(@text, '消息')]",
        # 雷军账号标识
        "//*[contains(@text, '雷军')]",
        # 发送操作
        "//*[contains(@text, '发送') and bbox_contains_point(@bounds, $point)]"
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

        # 需要至少私信操作(xpath[0])、雷军账号(xpath[1])、发送操作(xpath[2])
        if checked[0] and checked[1] and checked[2]:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 成功私信发送"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未完成私信发送"




def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 19,
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

    # 评估四个规则，级联关系：1->2->3->4
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)

    # 级联否决：上一级不满足则下一级不计分
    if not rule1_satisfied:
        rule2_satisfied = False
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule2_satisfied:
        rule3_satisfied = False
        rule4_satisfied = False
    elif not rule3_satisfied:
        rule4_satisfied = False

    # 计算最终分数
    max_score = 0.0
    if rule1_satisfied:
        max_score = 0.25
    if rule2_satisfied:
        max_score = 0.5
    if rule3_satisfied:
        max_score = 0.75
    if rule4_satisfied:
        max_score = 1.0

    # 构建详细信息
    details = [
        {
            "rule": "1. 打开抖音，查看雷军账号的粉丝数",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 打开B站，查看雷军账号的粉丝数",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 打开微博，查看雷军账号的粉丝数",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 私信发送给雷军的抖音账号",
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
        "BMK/first/44ba8898",
        "BMK/2026-04-29/抖音_b站_微博/BMK评测/f5aa6ee8-cdb2-4dff-bde5-2aecf7804ba3",
        "BMK/second/8382faaa",
        "BMK/third/ae1a8eeb",
        "BMK/fourth/51eed8b6"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 如果路径不存在，尝试评估第一个存在的路径
            if path == test_paths[0]:
                print(f"\n路径不存在: {path}")
            continue
