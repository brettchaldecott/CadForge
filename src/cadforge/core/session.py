"""Session persistence for CadForge.

Stores conversation transcripts as JSONL files with a session index
for resume and search.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cadforge.utils.paths import get_project_sessions_dir


@dataclass
class Message:
    """A single conversation message."""
    role: str  # "user", "assistant", "system"
    content: str | list[dict[str, Any]]
    timestamp: float = field(default_factory=time.time)
    tool_use_id: str | None = None
    tool_result: Any = None
    usage: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_use_id:
            d["tool_use_id"] = self.tool_use_id
        if self.tool_result is not None:
            d["tool_result"] = self.tool_result
        if self.usage:
            d["usage"] = self.usage
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Message:
        return cls(
            role=d["role"],
            content=d["content"],
            timestamp=d.get("timestamp", 0.0),
            tool_use_id=d.get("tool_use_id"),
            tool_result=d.get("tool_result"),
            usage=d.get("usage"),
        )


@dataclass
class SessionMetadata:
    """Metadata about a session for the index."""
    session_id: str
    started_at: str
    last_active: str
    message_count: int
    summary: str
    file_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionMetadata:
        return cls(**d)


class Session:
    """Manages a single conversation session with JSONL persistence."""

    def __init__(self, project_root: Path, session_id: str | None = None):
        self.project_root = project_root
        self.session_id = session_id or self._generate_id()
        self.sessions_dir = get_project_sessions_dir(project_root)
        self.file_path = self.sessions_dir / f"{self.session_id}.jsonl"
        self.messages: list[Message] = []
        self._loaded = False

    @staticmethod
    def _generate_id() -> str:
        return datetime.now(timezone.utc).strftime("session-%Y-%m-%d-%H-%M-%S")

    def add_message(self, message: Message) -> None:
        """Add a message and persist to disk."""
        self.messages.append(message)
        self._append_to_file(message)

    def add_user_message(self, content: str) -> Message:
        """Convenience method for adding a user message."""
        msg = Message(role="user", content=content)
        self.add_message(msg)
        return msg

    def add_assistant_message(
        self,
        content: str | list[dict[str, Any]],
        usage: dict[str, int] | None = None,
    ) -> Message:
        """Convenience method for adding an assistant message."""
        msg = Message(role="assistant", content=content, usage=usage)
        self.add_message(msg)
        return msg

    def _append_to_file(self, message: Message) -> None:
        """Append a single message to the JSONL file."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(message.to_dict()) + "\n")

    def load(self) -> None:
        """Load messages from JSONL file."""
        if not self.file_path.exists():
            return
        self.messages = []
        with open(self.file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.messages.append(Message.from_dict(json.loads(line)))
        self._loaded = True

    def get_api_messages(self) -> list[dict[str, Any]]:
        """Get messages formatted for the Anthropic API."""
        api_msgs = []
        for msg in self.messages:
            if msg.role in ("user", "assistant"):
                api_msgs.append({
                    "role": msg.role,
                    "content": msg.content,
                })
        return api_msgs

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def summary(self) -> str:
        """Generate a brief summary from the first user message."""
        for msg in self.messages:
            if msg.role == "user" and isinstance(msg.content, str):
                text = msg.content[:100]
                if len(msg.content) > 100:
                    text += "..."
                return text
        return "(empty session)"

    def to_metadata(self) -> SessionMetadata:
        """Generate metadata for the session index."""
        started = self.messages[0].timestamp if self.messages else time.time()
        last = self.messages[-1].timestamp if self.messages else started
        return SessionMetadata(
            session_id=self.session_id,
            started_at=datetime.fromtimestamp(started, timezone.utc).isoformat(),
            last_active=datetime.fromtimestamp(last, timezone.utc).isoformat(),
            message_count=self.message_count,
            summary=self.summary,
            file_path=str(self.file_path),
        )


class SessionIndex:
    """Manages the session index file for listing and resuming sessions."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.sessions_dir = get_project_sessions_dir(project_root)
        self.index_path = self.sessions_dir / "sessions-index.json"

    def _load_index(self) -> list[SessionMetadata]:
        if not self.index_path.exists():
            return []
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return [SessionMetadata.from_dict(d) for d in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save_index(self, entries: list[SessionMetadata]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps([e.to_dict() for e in entries], indent=2) + "\n",
            encoding="utf-8",
        )

    def update(self, session: Session) -> None:
        """Update or add a session in the index."""
        entries = self._load_index()
        metadata = session.to_metadata()

        # Replace existing entry or append
        for i, entry in enumerate(entries):
            if entry.session_id == metadata.session_id:
                entries[i] = metadata
                break
        else:
            entries.append(metadata)

        self._save_index(entries)

    def list_sessions(self, limit: int = 20) -> list[SessionMetadata]:
        """List recent sessions, most recent first."""
        entries = self._load_index()
        entries.sort(key=lambda e: e.last_active, reverse=True)
        return entries[:limit]

    def get_latest(self) -> SessionMetadata | None:
        """Get the most recent session."""
        entries = self.list_sessions(limit=1)
        return entries[0] if entries else None

    def get_by_id(self, session_id: str) -> SessionMetadata | None:
        """Find a session by its ID."""
        entries = self._load_index()
        for entry in entries:
            if entry.session_id == session_id:
                return entry
        return None
