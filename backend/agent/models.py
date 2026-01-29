from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class AgentStep(BaseModel):
    id: str
    type: Literal["plan", "tool", "analysis", "summary", "memory"]
    title: str
    detail: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    session_id: str
    query: str
    language: Literal["auto", "zh", "en"] = "auto"
    export_markdown: bool = False
    export_pdf: bool = False


class ChatResponse(BaseModel):
    reply: str
    steps: List[AgentStep]
    structured_data: Dict[str, Any] = {}
    markdown_report: Optional[str] = None
    # 导出 PDF 可以走前端打印或额外后端实现


class PdfParseResult(BaseModel):
    session_id: str
    filename: str
    metrics: Dict[str, Any]
    raw_preview: str
    steps: List[AgentStep]


class ExcelParseResult(BaseModel):
    session_id: str
    filename: str
    metrics: Dict[str, Any]
    steps: List[AgentStep]
