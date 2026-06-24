# todo-app

A simple command-line to-do app built with the Python standard library.

## Setup

Requires Python 3. No installation or third-party packages needed.

```
cd todo-app
```

## Usage

```
python todo.py add "<title>"   Add a task. Prints "Added task <id>".
python todo.py list            List all tasks as "<id>. [ ] <title>" (or "[x]" if done).
python todo.py done <id>       Mark a task complete. Prints "Completed task <id>".
python todo.py delete <id>     Delete a task. Prints "Deleted task <id>".
```

## Examples

```
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

On invalid input (missing title, unknown id, or bad command), the app prints a
clear error message to stderr and exits with code 1.
