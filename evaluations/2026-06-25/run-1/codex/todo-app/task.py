class Task:
    def __init__(self, task_id, title, done=False):
        self.id = task_id
        self.title = title
        self.done = done

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            int(data["id"]),
            str(data["title"]),
            bool(data["done"]),
        )
