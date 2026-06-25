"""Task data model."""


class Task:
    """A single to-do item with an id, title, and completion flag."""

    def __init__(self, id, title, done=False):
        self.id = id
        self.title = title
        self.done = done

    def to_dict(self):
        """Return a JSON-serializable dict for this task."""
        return {"id": self.id, "title": self.title, "done": self.done}

    @classmethod
    def from_dict(cls, data):
        """Build a Task from a dict produced by to_dict()."""
        return cls(id=data["id"], title=data["title"], done=data["done"])
