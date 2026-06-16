"""Load and save tasks to a JSON file."""
import json
import os
from task import Task

TASKS_FILE = "tasks.json"


def load_tasks() -> list:
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Task.from_dict(item) for item in data]


def save_tasks(tasks: list) -> None:
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)
