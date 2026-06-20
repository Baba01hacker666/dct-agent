"""
dct.tools.tasks
Task tracking system for the agent to organize complex requests.
"""

from __future__ import annotations
import threading
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str = "pending"  # pending, in_progress, completed
    active_form: Optional[str] = None


class TaskTracker:
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        # In a real app, you might save this in .dct/sessions/
        self.tasks: List[Task] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def create(
        self, subject: str, description: str, active_form: Optional[str] = None
    ) -> Task:
        with self._lock:
            task = Task(
                id=str(self._next_id),
                subject=subject,
                description=description,
                active_form=active_form,
            )
            self.tasks.append(task)
            self._next_id += 1
        return task

    def update(
        self,
        task_id: str,
        status: Optional[str] = None,
        subject: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Task]:
        with self._lock:
            for task in self.tasks:
                if task.id == task_id:
                    if status:
                        task.status = status
                    if subject:
                        task.subject = subject
                    if description:
                        task.description = description
                    return task
        return None

    def get_all(self) -> List[Task]:
        with self._lock:
            return list(self.tasks)

    def get(self, task_id: str) -> Optional[Task]:
        with self._lock:
            for task in self.tasks:
                if task.id == task_id:
                    return task
        return None

    def summary(self) -> str:
        with self._lock:
            tasks = list(self.tasks)
        if not tasks:
            return "No tasks."

        lines = ["[TASKS]"]
        for t in tasks:
            icon = "[ ]"
            if t.status == "in_progress":
                icon = "[~]"
            elif t.status == "completed":
                icon = "[x]"
            lines.append(f"{t.id}. {icon} {t.subject} ({t.status})")
        return "\n".join(lines)


# Global tracker for the REPL/Session
_tracker = None
_tracker_lock = threading.Lock()


def get_tracker() -> TaskTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = TaskTracker()
    return _tracker
