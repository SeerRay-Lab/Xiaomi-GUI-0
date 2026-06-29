import json
import os
import time
import traceback
import logging

import numpy as np
from PIL import Image, ImageDraw

from android_world.agents import base_agent
from android_world.env import interface
from android_world.env import json_action
from android_world.agents.cv_agent.llm_client import LLMClient
from android_world.agents.agent_english_final.response_parser import (
    parse_response,
    get_content,
)
from android_world.agents.cv_agent.action_converter import convert_to_json_action
from android_world.agents.cv_agent.image_utils import encode_screenshot

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
"""# Role
You are a GUI interaction agent. You perceive the screen, review prior steps, and decide the most reasonable next action to fulfill the user's instruction.

# Input Context
1. User instruction
2. Interaction history
3. Current device type & foreground app
4. Current screenshot

# Available Tools
You MUST pick exactly one tool per step. Output the corresponding JSON string inside `<tool_call>`.
1. Tap: `{"name": "Tap", "position": [x, y], "times": 1}` (Tap at coordinate)
2. LongPress: `{"name": "LongPress", "position": [x, y]}` (Trigger contextual menus)
3. Swipe: `{"name": "Swipe", "start_position": [x1, y1], "end_position": [x2, y2]}` (Swipe to scroll/move. Swipe up to scroll down)
4. Type: `{"name": "Type", "position": [x, y], "text": "..."}` (Tap input box and type)
5. Search: `{"name": "Search", "position": [x, y], "text": "..."}` (Macro: tap -> clear -> type -> submit)
6. Open: `{"name": "Open", "app": "..."}` (Launch app via system)
7. Back: `{"name": "Back"}` (System-level back)
8. Home: `{"name": "Home"}` (Go to home screen)
9. Wait: `{"name": "Wait"}` (Wait for page loading/rendering)
10. Request: `{"name": "Request", "text": "..."}` (Ask user for clarification/confirmation)
11. Fail: `{"name": "Fail", "type": "...", "reason": "..."}` (Report failure. `<TYPE>` MUST be one of: LOGIN_REQUIRED, USE_GUIDANCE, CAPTCHA_VERIFICATION, RESULT_NOT_FOUND, BLUETOOTH_CONNECTION_REQUIRED, NETWORK_ERROR, PAYMENT_AUTHENTICATION, TASK_CANT_FULLFILLED, REPEAT_OPERATION, PERMISSION_REQUEST, PASSWORD_REQUIRED, TAKEOVER_EXIT, TEMPORARY_TAKEOVER, MANUAL_VERIFICATION_REQUIRED)
12. Complete: `{"name": "Complete"}` (Confirm goal reached for non-Q&A tasks)
13. Speak: `{"name": "Speak", "text": "..."}` (Present final answer for Q&A tasks)


# Operational Constraints
1. Coordinate system: every `position` is a relative [x, y] in [0, 1] with 3-decimal precision. Top-left is (0, 0); bottom-right is (1, 1).
2. Dismiss unrelated pop-ups (ads, upgrade prompts, rating requests) by tapping their Close / Skip / X / "Later" button rather than calling Fail.
3. Loop breaker: if three consecutive steps cause no visible change, or the same action is repeating in a loop, self-correct (try Back or a different target). If self-correction fails, call Fail.

# Reasoning Framework (inside <think>)
Before emitting the action, reason inside `<think>...</think>` (omit steps if no new info):
1. [Observation]: Objectively describe the current App, page state, and key visible elements.
2. [Reflection]: (Optional) Include ONLY if the current screen deviates from the previous plan's expectation. Explain what was expected vs. what is actually seen.
3. [Plan] / [Plan Update] / [Replan]: (Choose one). Output a 2-4 step path in a single line separated by `|`. Mark completed steps with `✓` and the current step with `→`. Use [Replan] if the previous plan failed.
4. [Decision]: Deduce the exact action based on the Observation and the current `→` step in the Plan. 
5. [Memory]: Cache persistent info needed for future steps.

# Output Format
Your assistant message `content` MUST strictly follow this three-span XML-like shape, in this exact order, with no extra text before, between, or after:
<think>
[your observation, analysis and reasoning]
</think>
<action>
[a short natural-language description of the action, e.g., "Tap the search bar"]
</action>
<tool_call>
{"name": "Tap", "position": [0.521, 0.123], "times": 1}
</tool_call>"""
)


class AgentEnglishFinal(base_agent.EnvironmentInteractingAgent):
    """English Final Agent using <think><action><tool_call> format with flat JSON."""

    def __init__(
        self,
        env: interface.AsyncEnv,
        name: str = "agent_english_final",
        checkpoint_dir: str = None,
    ):
        super().__init__(env, name, transition_pause=None)
        self.history: list[dict] = []
        self.task_count = 0
        self.step_count = 0
        self.max_image_count = int(os.environ.get("CV_AGENT_MAX_IMAGES", "3"))
        self.max_turn_count = int(os.environ.get("CV_AGENT_MAX_TURNS", "10"))
        self.llm_client = LLMClient()
        self.verifier = None

        if checkpoint_dir is not None:
            basename = os.path.basename(checkpoint_dir)
        else:
            cur_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            basename = f"default_{cur_time}"
        self.save_dir = f"./agent_english_final_logs/{basename}"
        os.makedirs(self.save_dir, exist_ok=True)

    def reset(self, go_home: bool = False) -> None:
        super().reset(go_home)
        self.env.hide_automation_ui()
        self.history.clear()
        self.step_count = 0
        self.task_count += 1

    def _get_foreground_app(self) -> str:
        try:
            activity = self.env.foreground_activity_name
            if activity:
                return activity
        except Exception:
            pass
        return "未知"

    def _build_messages(self, goal: str, screenshot_b64: str) -> list[dict]:
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]

        history_slice = self.history[-self.max_turn_count:]
        image_start_idx = max(0, len(history_slice) - self.max_image_count)

        for idx, h in enumerate(history_slice):
            user_text = h.get("user_text", "")
            has_image = idx >= image_start_idx and h.get("screenshot_b64")

            if has_image:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{user_text}<image>"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{h['screenshot_b64']}"
                            },
                        },
                    ],
                })
            else:
                messages.append({"role": "user", "content": user_text})

            assistant_text = h.get("assistant_response", "")
            if not assistant_text:
                assistant_text = get_content(h.get("parsed_action", {}))
            messages.append({"role": "assistant", "content": assistant_text})

        foreground_app = self._get_foreground_app()
        extra_info = f"当前在手机设备，手机全屏下进行操作,处在{foreground_app}界面中"

        last_query = self.history[-1].get("query", "") if self.history else ""
        last_func = self.history[-1].get("last_func", "") if self.history else ""
        if last_query == goal and last_func != "Request" and self.history:
            current_query = extra_info
        else:
            current_query = f"{extra_info}\n用户请求：{goal}"

        current_user_content = [
            {"type": "text", "text": f"{current_query}<image>"},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{screenshot_b64}"
                },
            },
        ]
        messages.append({"role": "user", "content": current_user_content})

        return messages

    def _draw_action_on_screenshot(
        self, parsed_action: dict, pixels: np.ndarray
    ) -> Image.Image:
        img = Image.fromarray(pixels)
        draw = ImageDraw.Draw(img)
        h, w = pixels.shape[0], pixels.shape[1]
        func = parsed_action.get("func", "")

        def _to_abs(pos):
            x = int(pos[0] * w) if pos[0] <= 1 else int(pos[0])
            y = int(pos[1] * h) if pos[1] <= 1 else int(pos[1])
            return x, y

        if func in ("Tap", "LongPress", "Type", "Search"):
            pos = parsed_action.get("position", [0.5, 0.5])
            x, y = _to_abs(pos)
            r = 15
            draw.line([(x - r, y), (x + r, y)], fill="red", width=3)
            draw.line([(x, y - r), (x, y + r)], fill="red", width=3)
            draw.ellipse(
                [(x - 5, y - 5), (x + 5, y + 5)], fill="red", outline="red"
            )
            if func in ("Type", "Search"):
                text = parsed_action.get("text", "")
                draw.text((x + 20, y - 10), text[:50], fill="red")

        elif func == "Swipe":
            start = parsed_action.get("start_position", [0.5, 0.5])
            end = parsed_action.get("end_position", [0.5, 0.5])
            sx, sy = _to_abs(start)
            ex, ey = _to_abs(end)
            draw.line([(sx, sy), (ex, ey)], fill="blue", width=3)
            draw.ellipse(
                [(sx - 5, sy - 5), (sx + 5, sy + 5)], fill="green", outline="green"
            )
            draw.ellipse(
                [(ex - 5, ey - 5), (ex + 5, ey + 5)], fill="red", outline="red"
            )

        return img

    def _task_dir(self, task_name: str = None) -> str:
        if task_name is not None:
            return os.path.join(self.save_dir, task_name)
        return os.path.join(self.save_dir, f"task_{self.task_count:03d}")

    def save_step(self, save_info: dict, task_name: str = None) -> None:
        try:
            raw_pixels = save_info.get("raw_pixels")
            save_dir = self._task_dir(task_name)
            os.makedirs(save_dir, exist_ok=True)

            img_path = os.path.join(save_dir, f"step_{self.step_count:03d}.png")

            if self.step_count == 1 and os.path.exists(img_path):
                import glob
                for f in glob.glob(os.path.join(save_dir, "*")):
                    os.remove(f)

            parsed_action = save_info.get("parsed_action", {})
            if raw_pixels is not None:
                # Save original (unlabeled) screenshot
                raw_img = Image.fromarray(raw_pixels)
                raw_img_path = os.path.join(save_dir, f"step_{self.step_count:03d}_raw.png")
                raw_img.save(raw_img_path)
                # Save annotated screenshot
                annotated = self._draw_action_on_screenshot(
                    parsed_action, raw_pixels
                )
                annotated.save(img_path)

            info_to_save = {k: v for k, v in save_info.items() if k != "raw_pixels"}
            info_path = os.path.join(
                save_dir, f"step_{self.step_count:03d}.json"
            )
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(info_to_save, f, indent=2, ensure_ascii=False)
        except Exception:
            logger.error(f"save_step error:\n{traceback.format_exc()}")

    def save_result(
        self,
        is_success: float,
        task_name: str = None,
        final_success: float = 0,
    ) -> None:
        res = {
            "is_success": is_success,
            "final_success": final_success,
            "task_name": task_name,
        }
        save_dir = self._task_dir(task_name)
        os.makedirs(save_dir, exist_ok=True)
        res_path = os.path.join(save_dir, f"step_{self.step_count:03d}.result")
        with open(res_path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)

    def step(
        self, goal: str, verbose: bool = True, task_name: str = None
    ) -> base_agent.AgentInteractionResult:
        result = {
            "screenshot": None,
            "action": None,
            "parsed_action": None,
            "response": None,
        }
        self.step_count += 1
        save_info = {
            "task": goal,
            "step": self.step_count,
            "task_count": self.task_count,
        }
        err_info = ""

        # 1. Get screen state
        try:
            state = self.get_post_transition_state()
            result["screenshot"] = state.pixels
        except Exception:
            err_info += f"\n{traceback.format_exc()}\n"
            action = json_action.JSONAction(action_type=json_action.WAIT)
            return base_agent.AgentInteractionResult(done=False, data=result)

        # 2. Encode screenshot
        screenshot_b64 = encode_screenshot(state.pixels)

        # 3. Build messages
        messages = self._build_messages(goal, screenshot_b64)

        # 4. Call LLM
        try:
            content, raw_msg = self.llm_client.chat(messages)
            save_info["response"] = content
        except Exception:
            err_info += f"\n{traceback.format_exc()}\n"
            content, raw_msg = "", {}

        # 5. Parse response
        parsed = parse_response(content, raw_msg)
        result["parsed_action"] = parsed
        save_info["parsed_action"] = parsed

        if verbose:
            thought = parsed.get("thought", "")
            func = parsed.get("func", "")
            print(f"[AgentEnglishFinal] Step {self.step_count} | func={func}")
            if thought:
                display = thought[:200] + "..." if len(thought) > 200 else thought
                print(f"  thought: {display}")

        # 6. Convert to JSONAction
        screen_w, screen_h = state.pixels.shape[1], state.pixels.shape[0]
        try:
            action, is_terminal = convert_to_json_action(
                parsed, screen_w, screen_h
            )
            result["action"] = action.json_str()
            save_info["action"] = action.json_str()
        except Exception:
            err_info += f"\n{traceback.format_exc()}\n"
            action = json_action.JSONAction(action_type=json_action.UNKNOWN)
            is_terminal = False

        # 7. Handle multi-tap (times > 2)
        tap_times = int(parsed.get("times", 1)) if parsed.get("func") == "Tap" else 1
        try:
            self.env.execute_action(action)
            if tap_times > 2:
                import time as _time
                for _ in range(tap_times - 1):
                    _time.sleep(0.3)
                    self.env.execute_action(action)
        except Exception:
            err_info += f"\n{traceback.format_exc()}\n"

        # 8. Update history
        last_query = self.history[-1].get("query", "") if self.history else ""
        is_first_step = last_query != goal or not self.history
        user_text = goal if is_first_step else ""

        self.history.append({
            "screenshot_b64": screenshot_b64,
            "assistant_response": parsed.get("raw_model_output", content),
            "parsed_action": parsed,
            "query": goal,
            "user_text": user_text,
            "last_func": parsed.get("func", ""),
        })

        # 9. Save step
        save_info["raw_pixels"] = state.pixels
        save_info["err_info"] = err_info
        self.save_step(save_info, task_name)

        # 10. Return
        done = is_terminal or (
            action.action_type == json_action.ANSWER
            or action.action_type == json_action.STATUS
        )
        return base_agent.AgentInteractionResult(done=done, data=result)
