"""Small card-independent character canvas for ALD-like circuit boxes."""

class Canvas:
    def __init__(self, width, height, *, card_type):
        assert len(card_type) == 4 and card_type.isdigit()
        self.width = width
        self.card_type = card_type
        self.rows = [[" "] * width for _ in range(height)]
        self.boxes = []

    def put(self, x, y, char):
        assert 0 <= x < self.width and 0 <= y < len(self.rows)
        assert len(char) == 1
        self.rows[y][x] = char

    def text(self, x, y, value):
        for offset, char in enumerate(value):
            self.put(x + offset, y, char)

    def h(self, x1, x2, y):
        for x in range(x1, x2 + 1):
            old = self.rows[y][x]
            if old == " ": self.put(x, y, "─")
            elif old == "│": self.put(x, y, "┼")

    def v(self, x, y1, y2):
        for y in range(y1, y2 + 1):
            old = self.rows[y][x]
            if old == " ": self.put(x, y, "│")
            elif old == "─": self.put(x, y, "┼")

    def box(self, x, top, bottom, portion, function, circuit, *,
            wedge_in=None, wedge_out=None, input_count=0):
        assert top % 7 == 0
        assert bottom - top == max(6, input_count + 1)
        assert len(function) <= 6 and len(circuit) <= 6
        assert len(self.card_type + portion) <= 6
        assert all(xx != x or bottom < yy or top > bb for xx,yy,bb,_ in self.boxes)
        self.boxes.append((x, top, bottom, portion))
        self.text(x, top, "┌──────┐")
        self.text(x, bottom, "└──────┘")
        for y in range(top + 1, bottom):
            self.put(x, y, "◺" if y == wedge_in else "│")
            self.put(x + 7, y, "◺" if y == wedge_out else "│")
        self.text(x + 1, top + 1, function)
        self.text(x + 1, top + 3, circuit)
        self.text(x + 1, top + 4, self.card_type + portion)

    def render(self):
        return "\n".join("".join(row).rstrip() for row in self.rows)
