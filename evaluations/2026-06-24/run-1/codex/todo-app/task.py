class Task:
    def __init__(self, id, title, done=False):
        self.id = id
        self.title = title
        self.done = done

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=int(data["id"]),
            title=str(data["title"]),
            done=bool(data["done"]),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
        }
