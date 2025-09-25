import logging
from datetime import datetime
import shutil

class LazyLogger:
    """
    A powerful, colored, and multi-level logger.
    Initializes lazily and supports custom log levels for different application states.
    """

    # ANSI color codes for different log levels
    _COLORS = {
        "TRACE": "\033[37m",       # Grey
        "DEBUG": "\033[36m",       # Cyan
        "INFO": "\033[34m",        # Blue
        "SUCCESS": "\033[1;32m",    # Bright Green
        "EVENT": "\033[35m",       # Magenta
        "MODULE": "\033[1;35m",     # Bright Magenta
        "DATABASE": "\033[1;34m",    # Bright Blue
        "WARNING": "\033[33m",     # Yellow
        "SYSTEM": "\033[1;33m",     # Bright Yellow
        "ERROR": "\033[31m",       # Red
        "CRITICAL": "\033[1;31m",   # Bright Red
    }
    _RESET = "\033[0m"
    _CUSTOM_LEVELS_REGISTERED = False

    def __init__(self, name: str = "EnhancedLogger"):
        if not self._CUSTOM_LEVELS_REGISTERED:
            self._register_custom_levels()

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        # Lazy initialization for the handler
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    @classmethod
    def _register_custom_levels(cls):
        """Registers custom log levels with the logging module."""
        if cls._CUSTOM_LEVELS_REGISTERED:
            return
            
        logging.addLevelName(5, "TRACE")
        logging.addLevelName(25, "SUCCESS")
        logging.addLevelName(17, "EVENT")
        logging.addLevelName(16, "MODULE")
        logging.addLevelName(15, "DATABASE")
        logging.addLevelName(35, "SYSTEM") # Higher than WARNING
        
        cls._CUSTOM_LEVELS_REGISTERED = True

    def _log(self, level: str, message: str):
        """Internal log method with enhanced formatting."""
        level_value = logging.getLevelName(level)
        if not isinstance(level_value, int):
            # Fallback for invalid level names
            level_value = logging.INFO
            level = "INFO"

        timestamp = datetime.now().strftime("%H:%M:%S")
        color = self._COLORS.get(level, self._RESET)
        
        # Fixed-width level name for alignment
        level_display = f"[{level:<8}]"

        formatted_msg = f"{timestamp} {color}{level_display}:{self._RESET} {message}"
        self.logger.log(level_value, formatted_msg)

    def trace(self, message: str):
        """For extremely granular, step-by-step debugging information."""
        self._log("TRACE", message)
        
    def debug(self, message: str):
        """For detailed diagnostic information."""
        self._log("DEBUG", message)

    def info(self, message: str):
        """For general operational information."""
        self._log("INFO", message)

    def success(self, message: str):
        """For reporting successful operations or checks."""
        self._log("SUCCESS", message)

    def event(self, message: str):
        """For logging Discord gateway events (e.g., 'on_ready', 'on_guild_join')."""
        self._log("EVENT", message)

    def module(self, message: str):
        """For logging the loading, unloading, or reloading of modules/cogs."""
        self._log("MODULE", message)

    def database(self, message: str):
        """For logging database interactions (connections, queries, etc.)."""
        self._log("DATABASE", message)

    def warning(self, message: str):
        """For indicating potential issues that do not prevent operation."""
        self._log("WARNING", message)

    def system(self, message: str):
        """For critical system-level messages (e.g., startup, shutdown)."""
        self._log("SYSTEM", message)
        
    def error(self, message: str):
        """For reporting errors or exceptions that occurred during an operation."""
        self._log("ERROR", message)

    def critical(self, message: str):
        """For reporting severe errors that may lead to application termination."""
        self._log("CRITICAL", message)
        
    def header(self, text: str, color_key: str = "SYSTEM"):
        """Prints a large, centered header banner. Best for startup."""
        color = self._COLORS.get(color_key.upper(), self._COLORS["SYSTEM"])
        terminal_width = shutil.get_terminal_size().columns
        padding = (terminal_width - len(text) - 2) // 2
        
        print("\n" + color + "=" * terminal_width + self._RESET)
        print(color + " " * padding + f" {text} " + " " * padding + self._RESET)
        print(color + "=" * terminal_width + self._RESET + "\n")


# Singleton instance for easy import and use across the project
logger = LazyLogger()

# --- Example Usage ---
if __name__ == "__main__":
    logger.header("BOT INITIALIZING")
    logger.system("Starting Roxy Bot v2.0...")
    logger.module("Loading cog: music.py")
    logger.module("Loading cog: help.py")
    logger.success("All cogs loaded successfully.")
    logger.database("Connecting to database...")
    logger.success("Database connection established.")
    logger.event("Received event: ON_READY")
    logger.info("Bot is now online and ready.")
    logger.warning("Lavalink connection is unstable.")
    logger.trace("User 'KaiTy_Ez' used command 'ping'")
    logger.debug("Ping command returned latency: 42ms")
    logger.error("Failed to fetch track 'unknown song'.")
    logger.critical("Bot lost connection to Discord Gateway.")