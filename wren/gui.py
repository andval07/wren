"""tkinter window: address bar, back button, scrolling, clickable links."""

import tkinter
import tkinter.font

from .engine import load
from .layout import LINE_HEIGHT, DrawLine, DrawRect, DrawText
from .net import NetError

WIDTH, HEIGHT = 900, 700
SCROLL_STEP = 60
FAMILIES = {"sans-serif": "Helvetica", "serif": "Times", "monospace": "Courier"}


class TkMetrics:
    """Real font metrics from Tk, cached per font."""

    def __init__(self):
        self.cache = {}

    def get(self, font):
        if font not in self.cache:
            self.cache[font] = tkinter.font.Font(
                family=FAMILIES[font.family],
                size=-max(1, round(font.size)),  # negative size = pixels
                weight="bold" if font.bold else "normal",
                slant="italic" if font.italic else "roman",
            )
        return self.cache[font]

    def measure(self, text, font):
        return self.get(font).measure(text)

    def ascent(self, font):
        return self.get(font).metrics("ascent")

    def descent(self, font):
        return self.get(font).metrics("descent")


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.title("wren")
        bar = tkinter.Frame(self.window)
        bar.pack(fill="x")
        tkinter.Button(bar, text="<", command=self.back).pack(side="left")
        self.address = tkinter.Entry(bar)
        self.address.pack(side="left", fill="x", expand=True)
        self.address.bind("<Return>", lambda e: self.go(self.address.get()))
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT,
                                     bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.metrics = TkMetrics()
        self.history = []
        self.page = None
        self.scroll = 0
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.scroll_by(-SCROLL_STEP))
        self.canvas.bind("<Button-5>", lambda e: self.scroll_by(SCROLL_STEP))
        self.canvas.bind("<Button-1>", self.on_click)
        self.window.bind("<Down>", lambda e: self.scroll_by(SCROLL_STEP))
        self.window.bind("<Up>", lambda e: self.scroll_by(-SCROLL_STEP))
        self.window.bind("<Next>", lambda e: self.scroll_by(HEIGHT - 60))
        self.window.bind("<Prior>", lambda e: self.scroll_by(-(HEIGHT - 60)))

    def go(self, url, remember=True):
        try:
            page = load(url, self.canvas.winfo_width() or WIDTH, self.metrics)
        except (NetError, ValueError, UnicodeError) as e:
            self.show_error(url, e)
            return
        if remember and self.page is not None:
            self.history.append(str(self.page.url))
        self.page = page
        self.scroll = 0
        self.address.delete(0, "end")
        self.address.insert(0, str(page.url))
        self.window.title(f"{page.title or page.url} - wren")
        self.draw()

    def show_error(self, url, error):
        self.canvas.delete("all")
        self.canvas.create_text(10, 10, anchor="nw", fill="#a00000",
                                text=f"Could not load {url}\n\n{error}")

    def back(self):
        if self.history:
            self.go(self.history.pop(), remember=False)

    def max_scroll(self):
        if self.page is None:
            return 0
        return max(0, self.page.height - self.canvas.winfo_height())

    def scroll_by(self, delta):
        self.scroll = min(max(0, self.scroll + delta), self.max_scroll())
        self.draw()

    def on_wheel(self, event):
        self.scroll_by(-SCROLL_STEP if event.delta > 0 else SCROLL_STEP)

    def on_click(self, event):
        if self.page is None:
            return
        y = event.y + self.scroll
        for cmd in self.page.display_list:
            if not (isinstance(cmd, DrawText) and cmd.href):
                continue
            w = self.metrics.measure(cmd.text, cmd.font)
            h = cmd.font.size * LINE_HEIGHT
            if cmd.x <= event.x <= cmd.x + w and cmd.y <= y <= cmd.y + h:
                try:
                    target = self.page.url.resolve(cmd.href)
                except (NetError, ValueError) as e:
                    self.show_error(cmd.href, e)
                    return
                self.go(str(target))
                return

    def draw(self):
        self.canvas.delete("all")
        if self.page is None:
            return
        top = self.scroll
        bottom = self.scroll + self.canvas.winfo_height()
        for cmd in self.page.display_list:
            if isinstance(cmd, DrawText):
                if cmd.y > bottom or cmd.y + cmd.font.size * 2 < top:
                    continue
                self.canvas.create_text(cmd.x, cmd.y - top, anchor="nw",
                                        text=cmd.text, fill=cmd.color,
                                        font=self.metrics.get(cmd.font))
            elif isinstance(cmd, DrawRect):
                if cmd.y1 > bottom or cmd.y2 < top:
                    continue
                self.canvas.create_rectangle(cmd.x1, cmd.y1 - top, cmd.x2,
                                             cmd.y2 - top, width=0,
                                             fill=cmd.color)
            elif isinstance(cmd, DrawLine):
                if cmd.y1 > bottom or cmd.y1 < top:
                    continue
                self.canvas.create_line(cmd.x1, cmd.y1 - top, cmd.x2,
                                        cmd.y2 - top, fill=cmd.color)

    def run(self, url):
        self.window.update()
        self.go(url)
        self.window.mainloop()
