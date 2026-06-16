import argparse
import sys
from task import Task
from storage import load_tasks, save_tasks


def cmd_add(title):
    if not title or not title.strip():
        print("Error: title cannot be empty", file=sys.stderr)
        sys.exit(1)
    tasks = load_tasks()
    next_id = max((t.id for t in tasks), default=0) + 1
    tasks.append(Task(next_id, title))
    save_tasks(tasks)
    print(f"Added task {next_id}")


def cmd_list():
    tasks = load_tasks()
    for t in tasks:
        mark = "[x]" if t.done else "[ ]"
        print(f"{t.id}. {mark} {t.title}")


def cmd_done(task_id):
    tasks = load_tasks()
    for t in tasks:
        if t.id == task_id:
            t.done = True
            save_tasks(tasks)
            print(f"Completed task {task_id}")
            return
    print(f"Error: unknown task id {task_id}", file=sys.stderr)
    sys.exit(1)


def cmd_delete(task_id):
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        if t.id == task_id:
            del tasks[i]
            save_tasks(tasks)
            print(f"Deleted task {task_id}")
            return
    print(f"Error: unknown task id {task_id}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="todo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add")
    add_p.add_argument("title")

    subparsers.add_parser("list")

    done_p = subparsers.add_parser("done")
    done_p.add_argument("id", type=int)

    delete_p = subparsers.add_parser("delete")
    delete_p.add_argument("id", type=int)

    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(1)

    if args.command == "add":
        cmd_add(args.title)
    elif args.command == "list":
        cmd_list()
    elif args.command == "done":
        cmd_done(args.id)
    elif args.command == "delete":
        cmd_delete(args.id)
    else:
        print(f"Error: unknown command", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
