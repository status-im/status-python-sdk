from typing import Optional
import logging

class Logger:
    instance: Optional[logging.Logger] = None

    def __new__(cls) -> logging.Logger:

        if cls.instance:
            return cls.instance

        cls.instance = logging.getLogger("status-bot")
        cls.instance.setLevel(logging.INFO)
        cls.instance.propagate = False

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            f"[%(asctime)s] [%(levelname)s]\t%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        handler.setFormatter(formatter)
        cls.instance.addHandler(handler)
        return cls.instance
