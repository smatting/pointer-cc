class Box:
    def __init__(self, xmin, xmax, ymin, ymax):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax

    def __eq__(self, other):
        return self.totuple() == other.totuple()

    def totuple(self):
        return (self.xmin, self.xmax, self.ymin, self.ymax)

    def center(self):
        x = self.xmin + (self.xmax - self.xmin) // 2
        y = self.ymin + (self.ymax - self.ymin) // 2
        return (x, y)

    @property
    def width(self):
        return self.xmax - self.xmin

    @property
    def height(self):
        return self.ymax - self.ymin

def make_box(x, y, width, height):
    return box(x, x + width, y, y + height)

class Window:
    def __init__(self, pattern, name, box):
        self.pattern = pattern
        self.name = name
        self.box = box

    def totuple(self):
        return (self.pattern, self.name, self.box)

    def __eq__(self, other):
        if other is None:
            return False
        else:
            return self.totuple() == other.totuple()
