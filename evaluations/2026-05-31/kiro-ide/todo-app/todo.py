"""Entry point and CLI argument parsing for the to-do app."""
import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


def cmd_add(title: str) -> None:
    if not title or not title.strip():
        print("Error: title must not be empty", file=sys.stderr)
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="todo", description="A simple command-line to-do app.")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help='Add a task: add "<title>"')
    p_add.add_argument("title", help="Task title")

    sub.add_parser("list", help="List all tasks")

    p_done = sub.add_parser("done", help="Mark a task complete: done <id>")
    p_done.add_argument("id", help="Task id")

    p_delete = sub.add_parser("delete", help="Delete a task: delete <id>")
    p_delete.add_argument("id", help="Task id")

    # argparse exits with code 2 on parse errors. Override to exit 1 per spec.
    try:
        args = parser.parse_args()
    except SystemExit as e:
        if e.code != 0:
            sys.exit(1)
        raise

    if args.command is None:
        print("Error: missing command", file=sys.stderr)
        sys.exit(1)

    if args.command == "add":
        cmd_add(args.title)
    elif args.command == "list":
        cmd_list()
    elif args.command in ("done", "delete"):
        try:
            task_id = int(args.id)
        except ValueError:
            print(f"Error: id must be an integer, got '{args.id}'", file=sys.stderr)
            sys.exit(1)
        if args.command == "done":
            cmd_done(task_id)
        else:
            cmd_delete(task_id)
    else:
        print(f"Error: unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
