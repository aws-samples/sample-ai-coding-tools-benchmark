"""Task data model."""


class Task:
    """A single to-do task."""

    def __init__(self, id: int, title: str, done: bool = False):
        self.id = id
        self.title = title
        self.done = done

    def to_dict(self) -> dict:
        """Serialize the task to a JSON-compatible dict."""
        return {"id": self.id, "title": self.title, "done": self.done}

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Deserialize a task from a dict."""
        return cls(id=data["id"], title=data["title"], done=data["done"])
