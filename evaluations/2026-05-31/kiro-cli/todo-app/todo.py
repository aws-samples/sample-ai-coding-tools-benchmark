"""Command-line to-do app entry point."""

import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


def cmd_add(title: str) -> None:
    if not title:
        print("Error: title cannot be empty", file=sys.stderr)
        sys.exit(1)
    tasks = load_tasks()
    next_id = max((t.id for t in tasks), default=0) + 1
    tasks.append(Task(id=next_id, title=title, done=False))
    save_tasks(tasks)
    print(f"Added task {next_id}")


def cmd_list() -> None:
    tasks = load_tasks()
    for t in tasks:
        marker = "[x]" if t.done else "[ ]"
        print(f"{t.id}. {marker} {t.title}")


def cmd_done(task_id: int) -> None:
    tasks = load_tasks()
    for t in tasks:
        if t.id == task_id:
            t.done = True
            save_tasks(tasks)
            print(f"Completed task {task_id}")
            return
    print(f"Error: no task with id {task_id}", file=sys.stderr)
    sys.exit(1)


def cmd_delete(task_id: int) -> None:
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        if t.id == task_id:
            del tasks[i]
            save_tasks(tasks)
            print(f"Deleted task {task_id}")
            return
    print(f"Error: no task with id {task_id}", file=sys.stderr)
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo", description="A simple to-do app.")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="Add a task")
    p_add.add_argument("title", help="Task title")

    sub.add_parser("list", help="List all tasks")

    p_done = sub.add_parser("done", help="Mark a task complete")
    p_done.add_argument("id", type=int, help="Task id")

    p_delete = sub.add_parser("delete", help="Delete a task")
    p_delete.add_argument("id", type=int, help="Task id")

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    # argparse exits with code 2 on parse errors; convert that to code 1
    # with a stderr message to match the spec.
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        if e.code != 0:
            sys.exit(1)
        raise

    if args.command == "add":
        cmd_add(args.title)
    elif args.command == "list":
        cmd_list()
    elif args.command == "done":
        cmd_done(args.id)
    elif args.command == "delete":
        cmd_delete(args.id)
    else:
        print("Error: a command is required (add, list, done, delete)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
