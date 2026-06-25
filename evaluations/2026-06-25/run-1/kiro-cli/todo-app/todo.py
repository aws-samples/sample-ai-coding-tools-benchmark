"""Command-line to-do app entry point and CLI argument parsing."""

import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


def cmd_add(args):
    tasks = load_tasks()
    next_id = max((task.id for task in tasks), default=0) + 1
    tasks.append(Task(id=next_id, title=args.title))
    save_tasks(tasks)
    print("Added task {}".format(next_id))


def cmd_list(args):
    tasks = load_tasks()
    for task in tasks:
        mark = "x" if task.done else " "
        print("{}. [{}] {}".format(task.id, mark, task.title))


def cmd_done(args):
    tasks = load_tasks()
    for task in tasks:
        if task.id == args.id:
            task.done = True
            save_tasks(tasks)
            print("Completed task {}".format(args.id))
            return
    sys.stderr.write("Error: no task with id {}\n".format(args.id))
    sys.exit(1)


def cmd_delete(args):
    tasks = load_tasks()
    for task in tasks:
        if task.id == args.id:
            tasks.remove(task)
            save_tasks(tasks)
            print("Deleted task {}".format(args.id))
            return
    sys.stderr.write("Error: no task with id {}\n".format(args.id))
    sys.exit(1)


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on argument errors."""

    def error(self, message):
        sys.stderr.write("Error: {}\n".format(message))
        sys.exit(1)


def build_parser():
    parser = _Parser(description="A simple command-line to-do app.")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a task")
    add_parser.add_argument("title", help="Title of the task")
    add_parser.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser("list", help="List all tasks")
    list_parser.set_defaults(func=cmd_list)

    done_parser = subparsers.add_parser("done", help="Mark a task complete")
    done_parser.add_argument("id", type=int, help="ID of the task")
    done_parser.set_defaults(func=cmd_done)

    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("id", type=int, help="ID of the task")
    delete_parser.set_defaults(func=cmd_delete)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        sys.stderr.write("Error: no command given\n")
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
