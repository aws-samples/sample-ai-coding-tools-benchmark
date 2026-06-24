import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def next_id(tasks):
    if not tasks:
        return 1
    return max(task.id for task in tasks) + 1


def find_task(tasks, task_id):
    for task in tasks:
        if task.id == task_id:
            return task
    return None


def add_task(args):
    title = args.title
    if title is None or title == "":
        fail("Error: missing title")

    tasks = load_tasks()
    task = Task(next_id(tasks), title)
    tasks.append(task)
    save_tasks(tasks)
    print(f"Added task {task.id}")


def list_tasks(args):
    tasks = load_tasks()
    for task in tasks:
        marker = "[x]" if task.done else "[ ]"
        print(f"{task.id}. {marker} {task.title}")


def complete_task(args):
    tasks = load_tasks()
    task = find_task(tasks, args.id)
    if task is None:
        fail(f"Error: unknown task id {args.id}")

    task.done = True
    save_tasks(tasks)
    print(f"Completed task {args.id}")


def delete_task(args):
    tasks = load_tasks()
    task = find_task(tasks, args.id)
    if task is None:
        fail(f"Error: unknown task id {args.id}")

    tasks.remove(task)
    save_tasks(tasks)
    print(f"Deleted task {args.id}")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        fail(f"Error: {message}")


def build_parser():
    parser = Parser(prog="todo.py")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("title")
    add_parser.set_defaults(func=add_task)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(func=list_tasks)

    done_parser = subparsers.add_parser("done")
    done_parser.add_argument("id", type=int)
    done_parser.set_defaults(func=complete_task)

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("id", type=int)
    delete_parser.set_defaults(func=delete_task)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        fail("Error: bad command")
    args.func(args)


if __name__ == "__main__":
    main()
