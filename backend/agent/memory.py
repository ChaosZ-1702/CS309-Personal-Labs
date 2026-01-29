import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from .models import AgentStep
from config import MEMORY_FILE



class AgentMemory:
    def __init__(self, path: Path = MEMORY_FILE):
        self.path = path
        if not path.exists():
            path.write_text(json.dumps({"sessions": {}}, ensure_ascii=False, indent=2))

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"sessions": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_message(
        self, session_id: str, role: str, content: str
    ) -> None:
        data = self._load()
        sessions = data.setdefault("sessions", {})
        session = sessions.setdefault(
            session_id,
            {"created_at": datetime.utcnow().isoformat(), "messages": [], "files": [], "notes": []},
        )
        session["messages"].append(
            {"role": role, "content": content, "time": datetime.utcnow().isoformat()}
        )
        self._save(data)

    def add_step(self, session_id: str, step: AgentStep) -> None:
        data = self._load()
        sessions = data.setdefault("sessions", {})
        session = sessions.setdefault(
            session_id,
            {
                "created_at": datetime.utcnow().isoformat(),
                "messages": [],
                "steps": [],
                "files": [],
                "notes": [],
            },
        )
        session.setdefault("steps", [])
        # ✅ 用 mode="json"，自动把 datetime 等类型转成可序列化的值
        session["steps"].append(step.model_dump(mode="json"))
        self._save(data)


    def add_file_summary(self, session_id: str, info: Dict[str, Any]) -> None:
        data = self._load()
        sessions = data.setdefault("sessions", {})
        session = sessions.setdefault(
            session_id,
            {"created_at": datetime.utcnow().isoformat(), "messages": [], "files": [], "notes": []},
        )
        session.setdefault("files", [])
        session["files"].append(info)
        self._save(data)

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        return data.get("sessions", {}).get(session_id, {}).get("messages", [])

    def get_session_files(self, session_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        return data.get("sessions", {}).get(session_id, {}).get("files", [])

    def get_session_steps(self, session_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        return data.get("sessions", {}).get(session_id, {}).get("steps", [])
