"""Application entry point."""

from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import log
from .config import Config
from .main_window import MainWindow


def _install_sigint_handler(app: QApplication, window: MainWindow) -> None:
    """Make Ctrl-C from the terminal shut the app down cleanly.

    Qt's C++ event loop blocks the Python interpreter, so a SIGINT is never
    delivered to Python while ``app.exec()`` is running. Two things are needed:

    * a handler that closes the window (stopping capture threads) and quits, and
    * a no-op timer that fires often enough to return control to the interpreter
      so the queued signal actually gets a chance to run.
    """

    def _handle(_signum, _frame) -> None:
        sys.stderr.write("\nReceived interrupt — shutting down…\n")
        window.close()
        app.quit()

    signal.signal(signal.SIGINT, _handle)

    # Keep a reference on the window so the timer isn't garbage-collected.
    window._sigint_timer = QTimer(window)  # type: ignore[attr-defined]
    window._sigint_timer.timeout.connect(lambda: None)  # type: ignore[attr-defined]
    window._sigint_timer.start(200)  # type: ignore[attr-defined]


def main() -> int:
    log.setup()
    app = QApplication(sys.argv)
    app.setApplicationName("pySimpleView")
    config = Config()
    window = MainWindow(config)
    window.show()
    _install_sigint_handler(app, window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
