"""Source observations and canvas for the layered 5804191 Card-ALD."""

SLICES = [
    dict(bit="44", page="AP441", gates=[
        ("07", "U03AP", "D12", "J12"),
        ("08", "U03AP", "B10", "G07", "P3"),
        ("10", "U03AA", "D09", "D13", "P3"),
        ("09", "U03AA", "B12", "D11", "P3"),
        ("11", "U03AA", "J09", "D07"),
    ], join="12", net="D10", n=("31", "32"), n_out=("B09", "D07"),
         resistor=("42", "D13", "10"), term=("01", "D12")),
    dict(bit="45", page="AP451", gates=[
        ("13", "U03AP", "D04", "J12"),
        ("14", "U03AP", "B05", "G07", "P3"),
        ("16", "U03AA", "D09", "B03", "P3"),
        ("15", "U03AA", "D05", "B12", "P3"),
        ("17", "U03AA", "J09", "B07"),
    ], join="18", net="B04", n=("33", "34"), n_out=("B02", "B07"),
         resistor=("43", "B03", "16"), term=("02", "D04")),
    dict(bit="46", page="AP461", gates=[
        ("19", "U03AP", "J13", "J12"),
        ("20", "U03AP", "G12", "G07", "P3"),
        ("22", "U03AA", "D09", "J10", "P3"),
        ("21", "U03AA", "G13", "B12", "P3"),
        ("23", "U03AA", "J09", "J11"),
    ], join="24", net="G10", n=("36", "37"), n_out=("G09", "J11"),
         resistor=("40", "J10", "22"), term=("04", "J13")),
    dict(bit="47", page="AP471", gates=[
        ("25", "U03AP", "J12", "J04"),
        ("26", "U03AP", "G05", "G07", "J02"),
        ("28", "U03AA", "G02", "D09", "J02"),
        ("27", "U03AA", "J05", "B12", "J02"),
        ("29", "U03AA", "J09", "J07"),
    ], join="30", net="G03", n=("38", "39"), n_out=("G04", "J07"),
         resistor=("41", "G02", "28"), term=("05", "J04")),
]


class Canvas:
    def __init__(self, width=190, height=267):
        self.width = width
        self.rows = [[" "] * width for _ in range(height)]
        self.boxes = []

    def put(self, x, y, ch):
        assert 0 <= x < self.width and 0 <= y < len(self.rows), (x, y, ch)
        assert len(ch) == 1
        self.rows[y][x] = ch

    def text(self, x, y, value):
        for offset, ch in enumerate(value):
            self.put(x + offset, y, ch)

    def h(self, x1, x2, y):
        for x in range(x1, x2 + 1):
            if self.rows[y][x] == " ":
                self.put(x, y, "─")
            elif self.rows[y][x] == "│":
                self.put(x, y, "┼")

    def v(self, x, y1, y2):
        for y in range(y1, y2 + 1):
            if self.rows[y][x] == " ":
                self.put(x, y, "│")
            elif self.rows[y][x] == "─":
                self.put(x, y, "┼")

    def box(self, x, top, bottom, portion, function, circuit, *,
            wedge_in=None, wedge_out=None, input_count=0):
        # Seven rows including borders; add rows only for a sixth input or more.
        assert top % 7 == 0, (portion, top)
        assert bottom - top == max(6, input_count + 1)
        assert all(other_x != x or bottom < other_top or top > other_bottom
                   for other_x, other_top, other_bottom, _ in self.boxes)
        self.boxes.append((x, top, bottom, portion))
        self.put(x, top, "┌")
        self.h(x + 1, x + 6, top)
        self.put(x + 7, top, "┐")
        self.put(x, bottom, "└")
        self.h(x + 1, x + 6, bottom)
        self.put(x + 7, bottom, "┘")
        for y in range(top + 1, bottom):
            self.put(x, y, "◺" if y == wedge_in else "│")
            self.put(x + 7, y, "◺" if y == wedge_out else "│")
        self.text(x + 1, top + 1, function)
        self.text(x + 1, top + 3, circuit)
        self.text(x + 1, top + 4, f"4191{portion}")

    def render(self):
        return "\n".join("".join(row).rstrip() for row in self.rows)
