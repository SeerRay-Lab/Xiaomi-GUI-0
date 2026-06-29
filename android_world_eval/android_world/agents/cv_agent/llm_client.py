import os
import logging
import requests

logger = logging.getLogger(__name__)


class LLMClient:

    def __init__(
        self,
        model_url: str | None = None,
        model_name: str | None = None,
        timeout: int | None = None,
    ):
        self.model_url = model_url or os.environ.get("CV_AGENT_MODEL_URL", "")
        if not self.model_url:
            raise ValueError(
                "CV_AGENT_MODEL_URL environment variable is required"
            )
        self.model_name = model_name or os.environ.get(
            "CV_AGENT_MODEL_NAME", "base_model"
        )
        self.timeout = timeout or int(os.environ.get("CV_AGENT_TIMEOUT", "120"))
        self.api_key = os.environ.get("CV_AGENT_API_KEY", "")
        self.temperature = float(os.environ.get("CV_AGENT_TEMPERATURE", "0.0"))

    def chat(self, messages: list[dict]) -> tuple[str, dict]:
        """Send messages to the LLM and return (content_text, raw_message_dict)."""
        target_url = self.model_url
        if not target_url.endswith("/v1/chat/completions"):
            target_url = f"{target_url.rstrip('/')}/v1/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-Model-Provider-Id"] = os.environ.get("CV_AGENT_MODEL_PROVIDER", "vertex_ai")
        payload = {
            "model": self.model_name,
            "temperature": self.temperature,
            "top_p": 0.01 if self.temperature == 0.0 else 0.95,
            "top_k": 1 if self.temperature == 0.0 else 40,
            "messages": messages,
        }
        if not self.api_key:
            payload["separate_reasoning"] = False

        try:
            logger.info(f"Requesting model: {target_url} (Model: {self.model_name})")
            result = requests.post(
                target_url, headers=headers, json=payload, timeout=self.timeout
            )
            if result.status_code == 200:
                res_json = result.json()
                try:
                    message = res_json["choices"][0]["message"]
                    content = message.get("content") or ""
                    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
                    if reasoning:
                        # reasoning in separate field: prepend as <think>
                        stripped = content.lstrip()
                        if stripped.startswith("</think>"):
                            content = stripped[len("</think>"):].lstrip()
                        content = f"<think>{reasoning}</think>{content}"
                    elif "</think>" in content and "<think>" not in content:
                        # Model outputs think without opening tag
                        content = "<think>" + content
                    return content, message
                except (KeyError, IndexError):
                    logger.error(
                        f"Response struct error. Raw: {str(res_json)[:200]}..."
                    )
                    return "", {}
            else:
                logger.error(
                    f"API Error: {result.status_code} - {result.text[:200]}"
                )
                return "", {}
        except requests.Timeout:
            logger.error("API Error: Timeout")
            return "", {}
        except Exception as e:
            logger.error(f"Error in LLM request: {e}")
            return "", {}
