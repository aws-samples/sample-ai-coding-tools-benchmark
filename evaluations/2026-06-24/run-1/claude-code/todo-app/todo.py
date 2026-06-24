"""Command-line to-do app entry point and CLI argument parsing."""

import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on argument errors."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print("Error: {}".format(message), file=sys.stderr)
        sys.exit(1)


def cmd_add(title):
    tasks = load_tasks()
    next_id = max((task.id for task in tasks), default=0) + 1
    tasks.append(Task(id=next_id, title=title))
    save_tasks(tasks)
    print("Added task {}".format(next_id))


def cmd_list():
    tasks = load_tasks()
    for task in tasks:
        mark = "x" if task.done else " "
        print("{}. [{}] {}".format(task.id, mark, task.title))


def cmd_done(task_id):
    tasks = load_tasks()
    for task in tasks:
        if task.id == task_id:
            task.done = True
            save_tasks(tasks)
            print("Completed task {}".format(task_id))
            return
    print("Error: no task with id {}".format(task_id), file=sys.stderr)
    sys.exit(1)


def cmd_delete(task_id):
    tasks = load_tasks()
    for task in tasks:
        if task.id == task_id:
            tasks.remove(task)
            save_tasks(tasks)
            print("Deleted task {}".format(task_id))
            return
    print("Error: no task with id {}".format(task_id), file=sys.stderr)
    sys.exit(1)


def main():
    parser = ArgumentParser(description="A simple command-line to-do app.")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a task.")
    add_parser.add_argument("title", help="The task title.")

    subparsers.add_parser("list", help="List all tasks.")

    done_parser = subparsers.add_parser("done", help="Mark a task complete.")
    done_parser.add_argument("id", type=int, help="The task id.")

    delete_parser = subparsers.add_parser("delete", help="Delete a task.")
    delete_parser.add_argument("id", type=int, help="The task id.")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args.title)
    elif args.command == "list":
        cmd_list()
    elif args.command == "done":
        cmd_done(args.id)
    elif args.command == "delete":
        cmd_delete(args.id)
    else:
        parser.print_help(sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
