import json
import re
import logging

logger = logging.getLogger(__name__)

FUNC_REQUIRED_DICT = {
    "Open": ["app"],
    "Tap": ["position", "times"],
    "Type": ["position", "text"],
    "Search": ["position", "text"],
    "LongPress": ["position"],
    "Swipe": ["start_position", "end_position"],
    "Wait": [],
    "Speak": ["text"],
    "Request": ["text"],
    "Complete": [],
    "Fail": ["type", "reason"],
    "Back": [],
    "Home": [],
}

_COORD_KEYS = ("position", "start_position", "end_position")


def _normalize_coordinates(parsed: dict) -> dict:
    """If any coordinate value > 1, assume 1000x1000 space and divide by 1000."""
    for key in _COORD_KEYS:
        pos = parsed.get(key)
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            continue
        if any(v > 1 for v in pos):
            parsed[key] = [round(v / 1000.0, 3) for v in pos]
    return parsed


def get_content(label: dict) -> str:
    """Reconstruct assistant message in <think><action><tool_call> format.

    Uses flat JSON with "name" key: {"name": "Tap", "position": [...], "times": 1}
    """
    thought = label.get("thought", "")
    think = thought.split("<action>")[0].strip() if "<action>" in thought else thought.strip()
    action = (
        thought.split("<action>")[1].split("</action>")[0].strip()
        if "<action>" in thought
        else ""
    )

    func_name = label.get("func", "")
    tool_call = {"name": func_name}
    for key in FUNC_REQUIRED_DICT.get(func_name, []):
        if label.get(key) is not None:
            tool_call[key] = label[key]

    return (
        f"<think>{think}</think>"
        f"<action>{action}</action>"
        f"<tool_call>{json.dumps(tool_call, ensure_ascii=False)}</tool_call>"
    )


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rfind("```") > -1:
            text = text[: text.rfind("```")]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(text.replace("'", '"'))
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(m.group().replace("'", '"'))
        except json.JSONDecodeError:
            pass
    return None


def _flatten_tool_json(tc_json: dict) -> dict:
    """Convert tool_call JSON to flat dict with 'func' key.

    Handles both:
      - flat: {"name": "Tap", "position": [...], "times": 1}
      - nested: {"name": "Tap", "arguments": {"position": [...], "times": 1}}
    """
    func_name = tc_json.get("name", tc_json.get("func", ""))
    if "arguments" in tc_json:
        result = {"func": func_name}
        result.update(tc_json["arguments"])
    else:
        result = dict(tc_json)
        result.pop("name", None)
        result["func"] = func_name
    return result


def parse_response(response: str, message: dict | None = None) -> dict:
    """Parse model output in <think><action><tool_call> format with fallbacks."""
    if isinstance(response, dict):
        return response

    try:
        clean_response = response.strip()

        # 1. Extract <think>
        think_content = ""
        if "<think>" in clean_response:
            parts = clean_response.split("<think>", 1)
            if len(parts) > 1:
                think_parts = parts[1].split("</think>", 1)
                if think_parts:
                    think_content = think_parts[0].strip()

        if not think_content and message:
            if isinstance(message, dict):
                for key in message.keys():
                    if "reasoning" in key.lower():
                        think_content = message[key]
                        if isinstance(think_content, str):
                            think_content = think_content.strip()
                        break

        # 2. Extract <action>
        action_desc = ""
        if "<action>" in clean_response:
            parts = clean_response.split("<action>", 1)
            if len(parts) > 1:
                action_parts = parts[1].split("</action>", 1)
                if action_parts:
                    action_desc = action_parts[0].strip()

        # 3. Extract <tool_call> JSON
        command_json = None
        if "<tool_call>" in clean_response:
            parts = clean_response.split("<tool_call>", 1)
            if len(parts) > 1:
                tc_parts = parts[1].split("</tool_call>", 1)
                if tc_parts:
                    tc_json = _try_parse_json(tc_parts[0])
                    if tc_json:
                        command_json = _flatten_tool_json(tc_json)

        # 4. Fallback: <answer> format
        if command_json is None and "<answer>" in clean_response:
            parts = clean_response.split("<answer>", 1)
            if len(parts) > 1:
                answer_parts = parts[1].split("</answer>", 1)
                if answer_parts:
                    ans_json = _try_parse_json(answer_parts[0])
                    if ans_json:
                        command_json = _flatten_tool_json(ans_json) if "name" in ans_json else ans_json

        # 5. Fallback: raw JSON after tags
        if command_json is None:
            remaining = clean_response
            if "</think>" in remaining:
                remaining = remaining.split("</think>", 1)[-1].strip()
            if "</action>" in remaining:
                remaining = remaining.split("</action>", 1)[-1].strip()
            raw_json = _try_parse_json(remaining)
            if raw_json:
                command_json = _flatten_tool_json(raw_json) if "name" in raw_json else raw_json

        # Build result
        if command_json:
            result = dict(command_json)
            _normalize_coordinates(result)
            if action_desc:
                result["thought"] = f"{think_content}<action>{action_desc}</action>"
            else:
                result["thought"] = think_content
            result["raw_model_output"] = (
                response if isinstance(response, str) else str(response)
            )
            return result
        else:
            logger.warning("Failed to parse command_json, falling back to Wait")
            return {
                "thought": think_content if think_content else "Parse error, waiting.",
                "func": "Wait",
                "raw_model_output": response if isinstance(response, str) else str(response),
            }

    except Exception as e:
        logger.error(f"Response format error: {str(e)[:100]}...")
        return {
            "thought": "Parse exception, waiting.",
            "func": "Wait",
            "raw_model_output": response if isinstance(response, str) else str(response),
        }
