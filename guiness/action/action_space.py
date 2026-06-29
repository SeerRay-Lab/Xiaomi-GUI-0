# -*- coding: utf-8 -*-
"""
动作空间定义
提供对模型输出动作的验证和标准化功能
"""
import logging

logger = logging.getLogger(__name__)

# 定义允许的 Action Space
ACTION_REGISTRY = {
    "Tap": {"required": ["position"], "optional": ["times"]},
    "LongPress": {"required": ["position"]},
    "Swipe": {"required": [], "optional": ["start_position", "end_position", "position"]},
    "Type": {"required": ["position", "text"]},
    "Search": {"required": ["position", "text"]},
    "Open": {"required": ["app"]},
    "Back": {},
    "Wait": {},
    "Complete": {},
    "Fail": {"required":["type"], "optional": ["reason"]},
    "Speak": {"required": ["text"]},
    "ToolUse": {"required": ["type", "tool"]},
    # 向用户反问：模型需要澄清/补充信息。runner 会把它当软终止，
    # episode 退出但 conversation 进入 awaiting_user 状态等用户补充
    "Request": {"required": ["text"]},
}

def validate_action(action_dict):
    """
    验证动作是否合法
    Returns: (is_valid: bool, error_msg: str)
    """
    if not isinstance(action_dict, dict):
        return False, "Action 必须是一个字典"
        
    func = action_dict.get("func")
    if not func:
        return False, "缺少 'func' 字段"
        
    if func not in ACTION_REGISTRY:
        return False, f"未知的动作类型: {func}"
        
    schema = ACTION_REGISTRY[func]
    required = schema.get("required", [])
    
    for key in required:
        if key not in action_dict:
            return False, f"动作 {func} 缺少必需字段: {key}"
            
    # 特殊验证逻辑
    if func == "Swipe":
        has_coord = "start_position" in action_dict and "end_position" in action_dict
        has_dir = "position" in action_dict # 旧格式的 direction 保存在 position
        if not (has_coord or has_dir):
            return False, "Swipe 动作缺少滑动坐标或方向"
            
    return True, ""
    
def normalize_action(action_dict, width=0, height=0):
    """
    对 Action 参数进行标准化
    例如，将归一化坐标加上 `orig_position`，清理文本空格等
    """
    normalized = dict(action_dict)
    
    # 构建绝对坐标 (对齐老代码的逻辑)
    if width > 0 and height > 0:
        for pos_key in ["position", "start_position", "end_position"]:
            if pos_key in normalized and isinstance(normalized[pos_key], list) and len(normalized[pos_key]) >= 2:
                rel_x = normalized[pos_key][0]
                rel_y = normalized[pos_key][1]
                # 有时模型会输出百分比 0-1 的坐标
                abs_x = int(rel_x * width) if rel_x <= 1 else int(rel_x)
                abs_y = int(rel_y * height) if rel_y <= 1 else int(rel_y)
                normalized[f"orig_{pos_key}"] = [abs_x, abs_y]
                    
    return normalized
