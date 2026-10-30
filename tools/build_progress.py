"""One flushed, in-place stderr progress line per build step."""
import sys


class Progress:
    def __init__(self, label, stream=None):
        self.label = label
        self.stream = sys.stderr if stream is None else stream
        self.percent = -1
        self.closed = False
        self.failed = False

    def __enter__(self):
        self.update(0, 1)
        return self

    def update(self, completed, total):
        # Only successful context exit emits 100%, including empty steps.
        percent = min(99, max(0, int(100 * completed / total))) if total else 0
        if not self.closed and percent > self.percent:
            self._write(percent)

    def _write(self, percent, suffix=''):
        prefix = '\r' if self.percent >= 0 else ''
        self.stream.write(f'{prefix}{self.label}: {percent}%{suffix}')
        self.stream.flush()
        self.percent = percent

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None and not self.failed:
            self._write(100, '\n')
        else:
            self.stream.write(' (failed)\n')
            self.stream.flush()
        self.closed = True
