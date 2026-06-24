"""Command-line to-do app entry point and CLI argument parsing."""

import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


def cmd_add(args):
    title = args.title
    if not title or not title.strip():
        print("Error: task title cannot be empty", file=sys.stderr)
        sys.exit(1)
    tasks = load_tasks()
    next_id = max((task.id for task in tasks), default=0) + 1
    tasks.append(Task(id=next_id, title=title))
    save_tasks(tasks)
    print(f"Added task {next_id}")


def cmd_list(args):
    tasks = load_tasks()
    for task in tasks:
        mark = "x" if task.done else " "
        print(f"{task.id}. [{mark}] {task.title}")


def cmd_done(args):
    tasks = load_tasks()
    for task in tasks:
        if task.id == args.id:
            task.done = True
            save_tasks(tasks)
            print(f"Completed task {args.id}")
            return
    print(f"Error: no task with id {args.id}", file=sys.stderr)
    sys.exit(1)


def cmd_delete(args):
    tasks = load_tasks()
    for task in tasks:
        if task.id == args.id:
            tasks.remove(task)
            save_tasks(tasks)
            print(f"Deleted task {args.id}")
            return
    print(f"Error: no task with id {args.id}", file=sys.stderr)
    sys.exit(1)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)


def build_parser():
    parser = _Parser(description="A simple command-line to-do app.")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a task.")
    add_parser.add_argument("title", help="Title of the task.")
    add_parser.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser("list", help="List all tasks.")
    list_parser.set_defaults(func=cmd_list)

    done_parser = subparsers.add_parser("done", help="Mark a task complete.")
    done_parser.add_argument("id", type=int, help="Id of the task.")
    done_parser.set_defaults(func=cmd_done)

    delete_parser = subparsers.add_parser("delete", help="Delete a task.")
    delete_parser.add_argument("id", type=int, help="Id of the task.")
    delete_parser.set_defaults(func=cmd_delete)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        print("Error: no command given", file=sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
