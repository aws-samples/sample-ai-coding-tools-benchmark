# todo-app

A minimal command-line to-do app written in Python using only the standard library.

## Setup

Requires Python 3.7+. No installation or third-party dependencies.

```
cd todo-app
```

## Usage

```
python todo.py add "<title>"     # Add a task
python todo.py list              # List all tasks
python todo.py done <id>         # Mark a task complete
python todo.py delete <id>       # Delete a task
```

### Examples

```
$ python todo.py add "Buy milk"
Added task 1

$ python todo.py add "Write report"
Added task 2

$ python todo.py list
1. [ ] Buy milk
2. [ ] Write report

$ python todo.py done 1
Completed task 1

$ python todo.py list
1. [x] Buy milk
2. [ ] Write report

$ python todo.py delete 2
Deleted task 2
```

## Storage

Tasks are persisted to `tasks.json` in the current working directory. Each task has:

- `id` — auto-incrementing integer
- `title` — string
- `done` — boolean

## Errors

On invalid input (missing title, unknown id, bad command), the app prints an error
to stderr and exits with code 1.
