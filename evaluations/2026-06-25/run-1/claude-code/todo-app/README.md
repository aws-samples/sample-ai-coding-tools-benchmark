# todo-app

A minimal command-line to-do app built with the Python standard library only.

## Setup

Requires Python 3.6 or newer. No installation or third-party packages needed.

```sh
cd todo-app
```

## Usage

Run commands with `python todo.py <command>`.

| Command | Description |
| --- | --- |
| `add "<title>"` | Add a task. Prints `Added task <id>`. |
| `list` | List all tasks as `<id>. [ ] <title>` (or `[x]` if done). |
| `done <id>` | Mark a task complete. Prints `Completed task <id>`. |
| `delete <id>` | Delete a task. Prints `Deleted task <id>`. |

### Examples

```sh
$ python todo.py add "Buy milk"
Added task 1

$ python todo.py add "Walk the dog"
Added task 2

$ python todo.py list
1. [ ] Buy milk
2. [ ] Walk the dog

$ python todo.py done 1
Completed task 1

$ python todo.py list
1. [x] Buy milk
2. [ ] Walk the dog

$ python todo.py delete 2
Deleted task 2
```

## Storage

Tasks are persisted to `tasks.json` in the current directory. Each task has an
auto-incrementing integer `id`, a `title` string, and a `done` boolean.

## Errors

On invalid input (missing title, unknown id, or an unrecognized command), the
app prints a clear error message to stderr and exits with code 1.
