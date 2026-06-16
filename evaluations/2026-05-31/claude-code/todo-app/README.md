# todo-app

A simple command-line to-do app in Python.

## Setup

Requires Python 3. No third-party dependencies.

## Usage

Run from inside the `todo-app` directory. Tasks are persisted to `tasks.json` in the current directory.

```
python todo.py add "<title>"      # Add a task
python todo.py list               # List all tasks
python todo.py done <id>          # Mark a task complete
python todo.py delete <id>        # Delete a task
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

## Errors

Invalid input (missing title, unknown id, bad command) prints an error to stderr and exits with code 1.
