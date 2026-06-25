import argparse
import sys

from storage import load_tasks, save_tasks
from task import Task


class TodoArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print("Error: " + message, file=sys.stderr)
        raise SystemExit(1)


def next_task_id(tasks):
    if not tasks:
        return 1
    return max(task.id for task in tasks) + 1


def find_task(tasks, task_id):
    for task in tasks:
        if task.id == task_id:
            return task
    return None


def fail(message):
    print("Error: " + message, file=sys.stderr)
    raise SystemExit(1)


def build_parser():
    parser = TodoArgumentParser(prog="todo.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("title")

    subparsers.add_parser("list")

    done_parser = subparsers.add_parser("done")
    done_parser.add_argument("id", type=int)

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("id", type=int)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        tasks = load_tasks()
    except ValueError as error:
        fail(str(error))

    if args.command == "add":
        task = Task(next_task_id(tasks), args.title, False)
        tasks.append(task)
        save_tasks(tasks)
        print("Added task " + str(task.id))
    elif args.command == "list":
        for task in tasks:
            status = "[x]" if task.done else "[ ]"
            print(str(task.id) + ". " + status + " " + task.title)
    elif args.command == "done":
        task = find_task(tasks, args.id)
        if task is None:
            fail("unknown task id " + str(args.id))
        task.done = True
        save_tasks(tasks)
        print("Completed task " + str(args.id))
    elif args.command == "delete":
        task = find_task(tasks, args.id)
        if task is None:
            fail("unknown task id " + str(args.id))
        tasks.remove(task)
        save_tasks(tasks)
        print("Deleted task " + str(args.id))
    else:
        fail("bad command")


if __name__ == "__main__":
    main()
