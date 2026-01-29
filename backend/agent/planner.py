import uuid
from typing import List
from datetime import datetime
from openai import OpenAI

from .models import AgentStep
from config import OPENAI_MODEL_MAIN, OPENAI_API_KEY, OPENAI_BASE_URL


SYSTEM_PLANNER = """You are a task planner for a financial data & news agent.
Given a user query in Chinese or English, list 3-6 high-level steps (in Chinese)
that explain how the agent will handle it, including:
- which data sources (market APIs, PDF/Excel parsing, news RSS) will be used,
- what analysis will be performed,
- what kind of summary will be returned.

Return markdown bullet list only.
"""


class Planner:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=OPENAI_API_KEY or None,
            base_url=OPENAI_BASE_URL or None,
        )

    def plan(self, query: str, context_brief: str = "") -> AgentStep:
        messages = [
            {"role": "system", "content": SYSTEM_PLANNER},
            {
                "role": "user",
                "content": f"用户问题：{query}\n\n上下文简要信息：{context_brief}",
            },
        ]
        try:
            completion = self.client.chat.completions.create(
                model=OPENAI_MODEL_MAIN,
                messages=messages,
                temperature=0.3,
            )
            content = completion.choices[0].message.content or ""
        except Exception as e:
            content = f"- 规划失败，使用默认流程。\n- 错误信息: {e}"

        return AgentStep(
            id=str(uuid.uuid4()),
            type="plan",
            title="任务规划",
            detail=content,
            # timestamp=datetime.utcnow(),
            timestamp=datetime.now(),
        )
