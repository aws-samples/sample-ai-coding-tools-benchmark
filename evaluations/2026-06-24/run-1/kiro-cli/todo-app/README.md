# todo-app

A simple command-line to-do app built with the Python standard library.

## Setup

Requires Python 3. No third-party packages needed.

```
cd todo-app
```

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

Tasks are persisted to `tasks.json` in the current directory.
