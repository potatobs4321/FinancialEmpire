from datetime import datetime
from enum import Enum
import os

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class Logger(object):
    file_name = ""
    temp_log = []

    @classmethod
    def write_log(cls, log_level, content):
        cls.init_file_name()
        log_str = cls.make_log(log_level, content)
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
        os.makedirs(log_dir, exist_ok=True)

        cls.file_name = os.path.join(os.getcwd(), log_dir, cls.file_name)
        print(cls.file_name)
        # os.makedirs(cls.file_name, exist_ok=True)

    @classmethod
    def make_log(cls, log_level, content):
        now = datetime.now()
        log_str = now.strftime("%Y-%m-%d %H:%M:%S")
        log_str += " | "
        log_str += log_level.value
        log_str += " | "
        log_str += content
        return log_str

    @classmethod
    def flush(cls, force=False):
        if len(cls.temp_log) >= 500 or force:
            with open(cls.file_name, "w", encoding='utf-8') as f:
                for log_str in cls.temp_log:
                    f.write(log_str + "\n")


def main():
    for i in range(500):
        Logger.write_log(LogLevel.DEBUG, "Hello")
    return


if __name__ == "__main__":
    main()

