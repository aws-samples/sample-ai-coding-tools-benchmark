import argparse

from storage import load_tasks, save_tasks
from task import Task


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(1, f"Error: {message}\n")


def find_task(tasks, task_id):
    for task in tasks:
        if task.id == task_id:
            return task
    return None


def build_parser():
    parser = ArgumentParser(description="Manage a to-do list.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a task")
    add_parser.add_argument("title")

    subparsers.add_parser("list", help="List all tasks")

    done_parser = subparsers.add_parser("done", help="Mark a task complete")
    done_parser.add_argument("id", type=int)

    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("id", type=int)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        tasks = load_tasks()

        if args.command == "add":
            task_id = max((task.id for task in tasks), default=0) + 1
            tasks.append(Task(task_id, args.title))
            save_tasks(tasks)
            print(f"Added task {task_id}")
        elif args.command == "list":
            for task in tasks:
                marker = "x" if task.done else " "
                print(f"{task.id}. [{marker}] {task.title}")
        elif args.command == "done":
            task = find_task(tasks, args.id)
            if task is None:
                parser.error(f"unknown task id {args.id}")
            task.done = True
            save_tasks(tasks)
            print(f"Completed task {args.id}")
        elif args.command == "delete":
            task = find_task(tasks, args.id)
            if task is None:
                parser.error(f"unknown task id {args.id}")
            tasks.remove(task)
            save_tasks(tasks)
            print(f"Deleted task {args.id}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
