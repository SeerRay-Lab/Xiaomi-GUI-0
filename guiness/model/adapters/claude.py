# -*- coding: utf-8 -*-
from model.adapters import AdapterBase
from model.adapters._common import build_messages_standard
from model.response_parser import parse_model_response


class ClaudeAdapter(AdapterBase):
    name = "claude"

    def build_messages(self, **kwargs) -> list[dict]:
        return build_messages_standard(**kwargs)

    def parse_response(self, content, message=None) -> dict:
        return parse_model_response(content, message=message)

    def payload_extras(self) -> dict:
        return {"temperature": 0.0, "top_p": 0.01}
