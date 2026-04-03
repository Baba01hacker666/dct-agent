"""
dct.tools.tasks
Task tracking system for the agent to organize complex requests.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict
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

    def create(self, subject: str, description: str, active_form: Optional[str] = None) -> Task:
        task = Task(
            id=str(self._next_id),
            subject=subject,
            description=description,
            active_form=active_form
        )
        self.tasks.append(task)
        self._next_id += 1
        return task

    def update(self, task_id: str, status: Optional[str] = None, subject: Optional[str] = None, description: Optional[str] = None) -> Optional[Task]:
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
        return self.tasks

    def get(self, task_id: str) -> Optional[Task]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def summary(self) -> str:
        if not self.tasks:
            return "No tasks."
        
        lines = ["[TASKS]"]
        for t in self.tasks:
            icon = "[ ]"
            if t.status == "in_progress":
                icon = "[~]"
            elif t.status == "completed":
                icon = "[x]"
            lines.append(f"{t.id}. {icon} {t.subject} ({t.status})")
        return "\n".join(lines)

# Global tracker for the REPL/Session
_tracker = TaskTracker()

def get_tracker() -> TaskTracker:
    return _tracker
