# todo-app

A minimal command-line to-do app written in Python using only the standard library.

## Requirements

- Python 3.7+

No third-party packages are needed.

## Setup

Clone or copy this folder, then run commands from inside it:

```
cd todo-app
```

Tasks are stored in `tasks.json` in the current working directory.

## Usage

Add a task:

```
python todo.py add "Buy groceries"
```

List all tasks:

```
python todo.py list
```

Output format:

```
1. [ ] Buy groceries
2. [x] Walk the dog
```

Mark a task complete:

```
python todo.py done 1
```

Delete a task:

```
python todo.py delete 2
```

## Files

- `todo.py` — entry point and CLI argument parsing
- `storage.py` — load and save tasks to `tasks.json`
- `task.py` — `Task` data model
- `README.md` — this file

## Errors

On invalid input (missing title, unknown id, bad command), an error message is printed to stderr and the process exits with code 1.
