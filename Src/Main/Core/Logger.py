from datetime import datetime
from enum import Enum
from pathlib import Path

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class Logger(object):
    file_name = ""
    temp_log = []
    max_cache_len = 500

    @classmethod
    def write_log(cls, log_level, content):
        cls.init_file_name()
        log_str = cls.make_log_str(log_level, content)
        cls.temp_log.append(log_str)
        cls.flush()

    @classmethod
    def init_file_name(cls):
        if cls.file_name != "":
            return

        now = datetime.now()
        formatted = now.strftime("%Y_%m_%d(%H%M%S)")
        cls.file_name = "FELog_" + formatted + ".txt"
        log_dir = "Logs"
        current_file = Path(__file__).resolve()

        project_root_path = current_file.parent.parent.parent
        Path(project_root_path / log_dir).mkdir(parents=True, exist_ok=True)
        cls.file_name = project_root_path / log_dir / cls.file_name
        print(cls.file_name)
        # os.makedirs(cls.file_name, exist_ok=True)

    @classmethod
    def make_log_str(cls, log_level, content):
        now = datetime.now()
        log_str = now.strftime("%Y-%m-%d %H:%M:%S")
        log_str += " | "
        log_str += log_level.value
        log_str += " | "
        log_str += content
        return log_str

    @classmethod
    def flush(cls, force=False):
        if not cls.temp_log:
            return
        if not force and len(cls.temp_log) < cls.max_cache_len:
            return
        if cls.file_name == "":
            cls.init_file_name()
        with open(cls.file_name, "a", encoding="utf-8") as f:
            for log_str in cls.temp_log:
                f.write(log_str + "\n")
        cls.temp_log.clear()

    @classmethod
    def set_max_cache_len(cls, cache_len):
        cls.max_cache_len = cache_len


def main():
    Logger.set_max_cache_len(50)
    for i in range(500):
        Logger.write_log(LogLevel.DEBUG, "Hello")
    return


if __name__ == "__main__":
    main()

