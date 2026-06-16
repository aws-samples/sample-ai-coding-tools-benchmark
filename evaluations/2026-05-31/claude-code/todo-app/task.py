class Task:
    def __init__(self, id, title, done=False):
        self.id = id
        self.title = title
        self.done = done

    def to_dict(self):
        return {"id": self.id, "title": self.title, "done": self.done}

    @staticmethod
    def from_dict(data):
        return Task(data["id"], data["title"], data["done"])
