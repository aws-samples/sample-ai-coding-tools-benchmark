"""Task data model."""


class Task:
    def __init__(self, id, title, done=False):
        self.id = id
        self.title = title
        self.done = done

    def to_dict(self):
        return {"id": self.id, "title": self.title, "done": self.done}

    @classmethod
    def from_dict(cls, data):
        return cls(id=data["id"], title=data["title"], done=data["done"])
