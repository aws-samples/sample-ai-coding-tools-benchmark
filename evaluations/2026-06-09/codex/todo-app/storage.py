import json

from task import Task


TASKS_FILE = "tasks.json"


def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return []

    return [Task.from_dict(item) for item in data]


def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as file:
        json.dump([task.to_dict() for task in tasks], file, indent=2)
        file.write("\n")
