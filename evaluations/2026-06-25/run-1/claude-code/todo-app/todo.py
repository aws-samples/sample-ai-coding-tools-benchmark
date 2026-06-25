"""Command-line to-do app: entry point and CLI argument parsing."""

import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


class TodoArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 (not 2) on parse errors."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def cmd_add(args):
    tasks = load_tasks()
    new_id = max((task.id for task in tasks), default=0) + 1
    tasks.append(Task(id=new_id, title=args.title))
    save_tasks(tasks)
    print(f"Added task {new_id}")


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
    for index, task in enumerate(tasks):
        if task.id == args.id:
            del tasks[index]
            save_tasks(tasks)
            print(f"Deleted task {args.id}")
            return
    print(f"Error: no task with id {args.id}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = TodoArgumentParser(description="A simple command-line to-do app.")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a task")
    add_parser.add_argument("title", help="Task title")
    add_parser.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser("list", help="List all tasks")
    list_parser.set_defaults(func=cmd_list)

    done_parser = subparsers.add_parser("done", help="Mark a task complete")
    done_parser.add_argument("id", type=int, help="Task id")
    done_parser.set_defaults(func=cmd_done)

    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("id", type=int, help="Task id")
    delete_parser.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    if not args.command:
        print(
            "Error: no command provided. Use add, list, done, or delete.",
            file=sys.stderr,
        )
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
