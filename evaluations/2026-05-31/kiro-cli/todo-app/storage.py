"""Load and save tasks to a JSON file."""

import json
import os
from typing import List

from task import Task

STORAGE_FILE = "tasks.json"


def load_tasks() -> List[Task]:
    """Load tasks from the JSON file. Returns an empty list if the file does not exist."""
    if not os.path.exists(STORAGE_FILE):
        return []
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Task.from_dict(item) for item in data]


def save_tasks(tasks: List[Task]) -> None:
    """Save tasks to the JSON file."""
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)
