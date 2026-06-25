# todo-app

A simple command-line to-do app built with the Python standard library.

## Requirements

- Python 3 (standard library only; no third-party packages)

## Setup

No installation needed. Clone or copy the files and run `todo.py` directly.

```
cd todo-app
```

Tasks are persisted to `tasks.json` in the current directory.

## Usage

Add a task:

```
python todo.py add "Buy groceries"
```

List all tasks:

```
python todo.py list
```

Mark a task complete:

```
python todo.py done 1
```

Delete a task:

```
python todo.py delete 1
```

## Output format

- `add` prints `Added task <id>`
- `list` prints each task as `<id>. [ ] <title>` (or `[x]` if done)
- `done` prints `Completed task <id>`
- `delete` prints `Deleted task <id>`

On invalid input (missing title, unknown id, or bad command), an error message
is written to stderr and the program exits with code 1.
