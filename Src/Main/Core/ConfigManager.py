import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from Src.Main.Core.Logger import Logger, LogLevel


class ConfigManager:
    """界面配置的读写，持久化为 JSON 文件（默认 Src/Config/config.json）。

    存储按 section 分层，方便后续追加新配置项而不影响已有内容：

        {
            "window": {"width": 1320, "height": 880}
        }

    新增一项配置只需要两步：在 ``DEFAULTS`` 里加上 `section -> key -> 默认值`，
    然后调用 ``get`` / ``set``。类型校验以默认值的类型为准，手改文件塞进
    类型不符的值会被忽略并回退到默认值。

    本类刻意不依赖 Qt：屏幕尺寸裁剪之类的界面逻辑留给调用方，
    这样它可以在无界面环境下单独测试。
    """

    FILE_NAME = "config.json"
    DIR_NAME = "Config"

    DEFAULTS: Dict[str, Dict[str, Any]] = {
        "window": {"width": 1320, "height": 880},
        # 分割条尺寸，对应三块面板：左右是「摆盘 | 右侧」，右侧上下是「价格走势 / 预期分布」。
        # 数值是按默认窗口大小（1320x880）调好的；窗口更大时多出的空间仍由 stretchFactor 分配。
        # 写成 null 表示不干预，完全交给 stretchFactor。
        "layout": {
            "main_splitter": [435, 856],
            "right_splitter": [371, 365],
        },
    }

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else self._default_path()
        self._data: Dict[str, Dict[str, Any]] = {}
        # 先看文件原本在不在，再加载：load() 失败有两种原因（文件缺失 / 内容损坏），
        # 只有前者才补写默认值；后者原样留着，给用户查看和手改的余地。
        existed = self.path.exists()
        self.load()
        # 首次运行就把默认配置落盘。若等到第一次拖拽窗口才创建，
        # 目录和文件会迟迟不出现，容易让人以为功能没生效。
        if not existed:
            self.save()

    @classmethod
    def _default_path(cls) -> Path:
        # 本文件位于 Src/Main/Core/ConfigManager.py，向上三级即 Src 目录
        src_root = Path(__file__).resolve().parents[2]
        return src_root / cls.DIR_NAME / cls.FILE_NAME

    @staticmethod
    def _accepts(value: Any, default: Any) -> bool:
        """判断读到的值是否可用。

        以默认值的类型为准；bool 是 int 的子类，要单独挡掉。
        默认值是列表时（分割条尺寸），要求元素个数一致且全为整数。
        """
        if isinstance(default, bool):
            return isinstance(value, bool)
        if isinstance(default, list):
            # null 表示"不干预"：分割比例交由界面的 stretchFactor 决定
            if value is None:
                return True
            if not isinstance(value, list) or len(value) != len(default):
                return False
            return all(isinstance(item, int) and not isinstance(item, bool) for item in value)
        return isinstance(value, type(default)) and not isinstance(value, bool)

    def load(self) -> bool:
        """从磁盘读取配置。

        文件不存在、无法解析或结构不对时回退到默认值并返回 False，
        调用方可以据此判断这是首次运行。
        """
        self._data = {section: dict(values) for section, values in self.DEFAULTS.items()}
        if not self.path.exists():
            return False

        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as error:
            Logger.write_log(LogLevel.WARNING, f"[CONFIG] 读取失败，改用默认值: {error}")
            return False

        if not isinstance(raw, dict):
            Logger.write_log(LogLevel.WARNING, "[CONFIG] 顶层不是 JSON 对象，改用默认值")
            return False

        for section, defaults in self.DEFAULTS.items():
            stored = raw.get(section)
            if not isinstance(stored, dict):
                continue
            for key, default in defaults.items():
                value = stored.get(key)
                if not self._accepts(value, default):
                    if value is not None:
                        Logger.write_log(
                            LogLevel.WARNING,
                            f"[CONFIG] {section}.{key} 类型不符，忽略并沿用默认值",
                        )
                    continue
                self._data[section][key] = value
        return True

    def save(self) -> bool:
        """写回磁盘。先写临时文件再原子替换，避免中途崩溃留下半个文件。"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_name(self.path.name + ".tmp")
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)
            return True
        except OSError as error:
            Logger.write_log(LogLevel.WARNING, f"[CONFIG] 写入失败: {error}")
            return False

    def get(self, section: str, key: str) -> Any:
        return self._data.get(section, {}).get(key)

    def set(self, section: str, key: str, value: Any) -> None:
        self._data.setdefault(section, {})[key] = value

    def as_dict(self) -> Dict[str, Dict[str, Any]]:
        return {section: dict(values) for section, values in self._data.items()}
