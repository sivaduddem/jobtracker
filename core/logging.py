"""Pretty colored logging for the Internship Intelligence Platform."""

from __future__ import annotations

import logging
import sys
from typing import Final


class Color:
    RESET: Final = "\033[0m"
    BOLD: Final = "\033[1m"
    DIM: Final = "\033[2m"
    RED: Final = "\033[31m"
    GREEN: Final = "\033[32m"
    YELLOW: Final = "\033[33m"
    BLUE: Final = "\033[34m"
    MAGENTA: Final = "\033[35m"
    CYAN: Final = "\033[36m"
    WHITE: Final = "\033[37m"
    GRAY: Final = "\033[90m"


LEVEL_COLORS = {
    logging.DEBUG: Color.GRAY,
    logging.INFO: Color.CYAN,
    logging.WARNING: Color.YELLOW,
    logging.ERROR: Color.RED,
    logging.CRITICAL: Color.BOLD + Color.RED,
}


class ColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = LEVEL_COLORS.get(record.levelno, Color.WHITE)
        level = f"{color}{record.levelname:<8}{Color.RESET}"
        name = f"{Color.DIM}{record.name}{Color.RESET}"
        msg = record.getMessage()

        # Highlight common status phrases
        msg = msg.replace("Found ", f"{Color.GREEN}Found {Color.RESET}")
        msg = msg.replace(" new", f"{Color.BOLD}{Color.GREEN} new{Color.RESET}")
        msg = msg.replace("Retrying", f"{Color.YELLOW}Retrying{Color.RESET}")
        msg = msg.replace("Recovered", f"{Color.GREEN}Recovered{Color.RESET}")
        msg = msg.replace("ERROR", f"{Color.RED}ERROR{Color.RESET}")

        asctime = self.formatTime(record, self.datefmt)
        return f"{Color.GRAY}{asctime}{Color.RESET} {level} {name}  {msg}"


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ColoredFormatter(datefmt="%H:%M:%S")
    )
    root.addHandler(handler)

    # Quieten noisy libs
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
