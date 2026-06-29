import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from evaluator_xpath import evaluate_action_xml
except ImportError:
    from mobilebench.eval.evaluator_xpath import evaluate_action_xml


QUERY = "抖音商城买一双30块钱以上销量最高的男士拖鞋"
TASK_ID = 17
STEPRULES = """评分规则（分阶段验证进度）

1. 打开抖音，进入商城 → 总分:0.25

2. 搜索"男士拖鞋"相关产品 → 总分:0.5

3. 找到价格30块以上、销量最高的产品 → 总分:0.75

4. 完成购买操作 → 总分:1.0

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
        if "plan" in step and "orig_position" in step["plan"]:
            position_temp = [
                int(step['plan']['orig_position'][0]),
                int(step['plan']['orig_position'][1])
            ]
        
        elif "plan" in step and "position" in step["plan"]:
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
    import xml.etree.ElementTree as ET

    # 一票否决条件1: 未打开抖音商城
    has_douyin = False
    has_shop = False

    # 一票否决条件2: 未搜索男士拖鞋
    has_search = False
    has_mens_slipper = False

    # 一票否决条件3: 点击了价格低于30元或非男士款商品
    clicked_low_price = False
    clicked_female = False

    # XPath用于检测点击了低于30元的产品
    low_price_xpath = "//*[(contains(@text, '¥') or contains(@text, '元')) and (contains(@text, '¥2') or contains(@text, '¥1') or contains(@text, '29') or contains(@text, '28') or contains(@text, '27') or contains(@text, '26') or contains(@text, '25') or contains(@text, '24') or contains(@text, '23') or contains(@text, '22') or contains(@text, '21') or contains(@text, '20') or contains(@text, '19') or contains(@text, '18') or contains(@text, '17') or contains(@text, '16') or contains(@text, '15') or contains(@text, '14') or contains(@text, '13') or contains(@text, '12') or contains(@text, '11') or contains(@text, '10')) and bbox_contains_point(@bounds, $point)]"

    female_xpath = "//*[(contains(@text, '女士') or contains(@text, '女款') or contains(@ocr_texts, '女士') or contains(@ocr_texts, '女款')) and bbox_contains_point(@bounds, $point)]"

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        try:
            # 检查包名和关键词
            for line in xml_string.split('\n'):
                # 检查是否打开了抖音(package包含'douyin'或'aweme')
                if 'package' in line:
                    if 'douyin' in line or 'aweme' in line or 'tiktok' in line or 'ugc.aweme' in line:
                        has_douyin = True

                # 检查是否进入商城(关键词: 商城、购物、shop)
                if ('商城' in line or '购物' in line or 'shop' in line or 'Shop' in line) and ('text' in line or 'ocr' in line):
                    has_shop = True

                # 检查是否搜索或进行了搜索操作
                if '搜索' in line or 'search' in line or '搜索框' in line:
                    has_search = True

                # 检查是否包含男士拖鞋相关关键词
                if (('男士' in line or '男' in line) and ('拖鞋' in line or '鞋' in line)):
                    has_mens_slipper = True
        except Exception as e:
            pass

        # 检查是否点击了低价产品（使用xpath + action验证）
        try:
            match_flag, _ = evaluate_action_xml(xml_string, low_price_xpath, action_dict)
            if match_flag == 1:
                clicked_low_price = True
        except:
            pass

        # 检查是否点击了女士款产品
        try:
            match_flag, _ = evaluate_action_xml(xml_string, female_xpath, action_dict)
            if match_flag == 1:
                clicked_female = True
        except:
            pass

    # 检查否决条件1：未打开抖音商城
    if not (has_douyin and has_shop):
        return True, "未打开抖音商城"

    # 检查否决条件2：未搜索男士拖鞋
    if not (has_search and has_mens_slipper):
        return True, "未搜索男士拖鞋"

    # 检查否决条件3：点击了价格低于30元的产品
    if clicked_low_price:
        return True, "点击了价格低于30元的产品"

    # 检查否决条件4：点击了非男士款商品
    if clicked_female:
        return True, "点击了非男士款商品"

    return False, ""


def evaluate_rule_1(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则1：打开抖音，进入商城"""
    rule1_xpaths = [
        "//*[contains(@package, 'ugc.aweme') or contains(@package, 'douyin') or contains(@package, 'aweme') or contains(@package, 'tiktok')]",
        "//*[contains(@text, '商城') or contains(@text, '购物') or contains(@text, 'shop') or contains(@ocr_texts, '商城')]"
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
            except:
                pass

        # 检查是否满足规则
        if sum(checked) >= len(rule1_xpaths):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 打开抖音进入商城"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule1_xpaths)}"

    return False, "未打开抖音商城"


def evaluate_rule_2(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则2：搜索"男士拖鞋"相关产品"""
    rule2_xpaths = [
        "//*[contains(@text, '男士') and contains(@text, '拖鞋') and contains(@class, 'EditText') ]"
    ]

    checked = [False] * len(rule2_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}


        # 检查所有xpath，不使用break，支持多xpath匹配
        for xpath_idx in range(len(rule2_xpaths)):
            #print("checked",checked, xpath_idx)
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

        # 检查是否满足规则
        if sum(checked) >= len(rule2_xpaths):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 搜索男士拖鞋"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule2_xpaths)}"

    return False, "未搜索男士拖鞋"


def evaluate_rule_3(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则3：找到价格30块以上、销量最高的产品"""
    rule3_xpaths = [
        # 销量关键词：销量、销、件已售等
        "//*[contains(@text, '男士') and contains(@text, '拖鞋') and contains(@class, 'EditText') ] and //*[(contains(@text, '销量') or contains(@ocr_texts, '销量')) and bbox_contains_point(../../@bounds, $point)]"
    ]

    checked = [False] * len(rule3_xpaths)
    evidence_steps = []

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
            except:
                pass

        # 检查是否满足规则
        if sum(checked) >= len(rule3_xpaths):
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 找到价格>=30元、销量最高的产品"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule3_xpaths)}"

    return False, "未找到符合条件的产品"


def evaluate_rule_4(xml_strings: List[str], actions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """规则4：完成购买操作"""
    rule4_xpaths = [
        # 购买操作相关关键词
        "//*[(contains(@text, '立即支付') or contains(@text, '立即购买') or contains(@text, '加入购物车') or contains(@text, '加购') or contains(@ocr_texts, '购买')) and bbox_contains_point(../@bounds, $point)]",
        # 下单/支付操作
        "//*[(contains(@text, '选择规格') ) and bbox_contains_point(../@bounds, $point)]"
    ]

    checked = [False] * len(rule4_xpaths)
    evidence_steps = []

    for i in range(len(xml_strings)):
        xml_string = xml_strings[i]
        action_dict = actions[i] if i < len(actions) else {"action": "click", "params": {"position": [0, 0]}}

        # 检查所有xpath，不使用break，支持多xpath匹配
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

        # 检查是否满足规则 - 至少有一个购买操作
        if sum(checked) >= 1:
            return True, f"步骤{','.join(map(str, sorted(set(evidence_steps))))}: 完成购买操作"

    if any(checked):
        return False, f"部分步骤满足: {sum(checked)}/{len(rule4_xpaths)}"

    return False, "未完成购买操作"


def evaluate_trajectory(path: str) -> dict:
    """
    参数：
        path: 轨迹目录路径
    返回：
        {
            "query": "...",
            "id": 17,
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


    # 依次评估各个规则
    rule1_satisfied, rule1_evidence = evaluate_rule_1(xml_strings, actions)
    rule2_satisfied, rule2_evidence = evaluate_rule_2(xml_strings, actions)
    rule3_satisfied, rule3_evidence = evaluate_rule_3(xml_strings, actions)
    rule4_satisfied, rule4_evidence = evaluate_rule_4(xml_strings, actions)

    # 依赖关系：规则依次递进，前一个不满足则后续不满足
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
            "rule": "1. 打开抖音，进入商城",
            "score": 0.25,
            "satisfied": rule1_satisfied,
            "evidence": rule1_evidence
        },
        {
            "rule": "2. 搜索\"男士拖鞋\"相关产品",
            "score": 0.5,
            "satisfied": rule2_satisfied,
            "evidence": rule2_evidence
        },
        {
            "rule": "3. 找到价格30块以上、销量最高的产品",
            "score": 0.75,
            "satisfied": rule3_satisfied,
            "evidence": rule3_evidence
        },
        {
            "rule": "4. 完成购买操作",
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
    # 支持多路径测试
    test_paths = [
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d83a52af",
        "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ae59f21f",
        "/main/guiagent/xiaoaidata/BMK/mai-ui/6635700e",
        "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c45fb373",
        "BMK/first/50d2ea56",
        "BMK/2026-04-29/抖音/BMK评测/350d2435-60f5-4ac2-b90c-254bc4740391",
        "BMK/second/b3168437",
        "BMK/third/8cab8f22",
        "BMK/fourth/adb713a3"
    ]

    for path in test_paths:
        if os.path.exists(path):
            print(f"\n评估路径: {path}")
            result = evaluate_trajectory(path=path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 如果没有找到任何路径，使用第一个作为示例
            print(f"\n评估路径: {test_paths[0]}")
            result = evaluate_trajectory(path=test_paths[0])
            print(json.dumps(result, ensure_ascii=False, indent=2))
