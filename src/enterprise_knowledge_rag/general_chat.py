from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class GeneralChatAgent:
    def __init__(self, client: Any, *, model: str, timeout_seconds: float) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    def answer(self, question: str, history: Sequence[dict[str, str]]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是企业运营助手的通用对话角色。可以回答一般知识、写作、学习和闲聊。"
                    "不得声称了解未提供的企业内部制度、经营数据或个人敏感信息；"
                    "遇到此类事实应提示交由企业知识或数据角色处理。回答简洁、直接。"
                ),
            },
            *list(history)[-6:],
            {"role": "user", "content": question},
        ]
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0.3,
            timeout=self._timeout_seconds,
            messages=messages,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("通用对话模型未返回有效内容")
        return content.strip()


class SynthesisAgent:
    def __init__(self, chat: GeneralChatAgent) -> None:
        self._chat = chat

    def synthesize(self, question: str, knowledge_answer: str, data_answer: str) -> str:
        prompt = (
            "请仅根据下面两类已验证结果回答原问题，不添加新数字或企业规则。"
            "分别说明数据发现、制度依据、综合判断和局限。\n"
            f"原问题：{question}\n数据结果：{data_answer}\n制度结果：{knowledge_answer}"
        )
        return self._chat.answer(prompt, ())
