"""Load and save tasks to a JSON file in the current directory."""

import json
import os

from task import Task

TASKS_FILE = "tasks.json"


def load_tasks():
    """Return the list of tasks from TASKS_FILE, or [] if it doesn't exist."""
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Task.from_dict(item) for item in data]


def save_tasks(tasks):
    """Write the list of tasks to TASKS_FILE as JSON."""
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump([task.to_dict() for task in tasks], f, indent=2)
