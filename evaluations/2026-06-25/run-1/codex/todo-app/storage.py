import json

from task import Task


TASKS_FILE = "tasks.json"


def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("could not load tasks.json") from error

    if not isinstance(data, list):
        raise ValueError("could not load tasks.json")

    try:
        return [Task.from_dict(item) for item in data]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("could not load tasks.json") from error


def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as file:
        json.dump([task.to_dict() for task in tasks], file, indent=2)
