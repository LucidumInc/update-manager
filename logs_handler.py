import glob
import itertools
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from itertools import groupby

import os
import re
import shutil
from loguru import logger
from slugify import slugify

from config_handler import get_lucidum_dir


class BaseLogsHandler:

    def get_logs(self):
        raise NotImplementedError


class FileLogsHandler(BaseLogsHandler):

    def __init__(self, filename: str, tail: int = 100) -> None:
        super().__init__()
        self._filename = filename
        self._tail = tail
        self._name = None

    @property
    def name(self) -> str:
        if self._name is None:
            name = slugify(self._filename, separator="_")
            self._name = f"{name}.log"
        return self._name

    def get_logs(self):
        logs = ""
        with open(self._filename) as f:
            for line in f.readlines()[-self._tail:]:
                logs = f"{logs}{line}"
        return logs


class CommandLogsHandler(BaseLogsHandler):

    def __init__(self, name: str, command: str) -> None:
        super().__init__()
        self._name = name
        self._command = command

    @property
    def name(self) -> str:
        return f"{self._name}.log"

    def get_logs(self):
        lucidum_dir = get_lucidum_dir()
        command = self._command.split()
        cp = subprocess.run(
            command,
            cwd=lucidum_dir,
            check=True,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return cp.stdout


def get_file_log_handlers_old(pathname: str, date_parser, date_level: int):
    def get_key(item: str):
        key_ = item
        for _ in range(date_level):
            key_ = os.path.dirname(key_)
        return key_
    files = glob.glob(pathname)
    files_ = sorted(files, key=get_key)
    handlers = []
    for _, value in groupby(files_, key=get_key):
        filename = date_latest = None
        for f in value:
            date_level_path = f
            for _ in range(date_level - 1):
                date_level_path = os.path.dirname(date_level_path)
            date_ = date_parser(os.path.basename(date_level_path))
            if date_latest is None:
                filename, date_latest = f, date_
            else:
                if date_ > date_latest:
                    filename, date_latest = f, date_

        handlers.append(FileLogsHandler(filename))
    return handlers


def get_file_log_handlers(pathname: str, **kwargs):
    placeholders = re.findall(r"\{\w+:.+\}", pathname)
    placeholders_values = []
    for placeholder in placeholders:
        name, value = placeholder[1:-1].split(":", 1)
        if name == "date":
            lookback_days = kwargs.get("lookback_days")
            lookback_days = lookback_days + 1 if lookback_days is not None and isinstance(lookback_days, int) else 1
            date_ = datetime.now(tz=timezone.utc)
            dates = [(placeholder, (date_ - timedelta(days=days)).strftime(value)) for days in range(lookback_days)]
            placeholders_values.append(dates)

    globs = []
    for replacements in itertools.product(*placeholders_values):
        path = pathname
        for replacement, value in replacements:
            path = path.replace(replacement, value)
        globs.append(path)

    handlers = []
    for glob_pattern in globs:
        files = glob.glob(glob_pattern)
        handlers.extend([FileLogsHandler(filename) for filename in files])
    return handlers


def get_logs(handlers: list):
    logs_dir = str(uuid.uuid4())
    os.makedirs(logs_dir, exist_ok=True)
    for handler in handlers:
        out = None
        try:
            out = handler.get_logs()
        except Exception as e:
            logger.exception("Failed to get logs for '{}' handler: {}", handler.name, str(e))
        if not out:
            continue
        with open(os.path.join(logs_dir, handler.name), "w+") as f:
            f.write(out)
    filename = f"logs_{logs_dir}.tar.gz"
    cmd = f"sudo tar -czvf {filename} --directory={logs_dir} ."
    subprocess.run(cmd.split(), check=True)
    shutil.rmtree(logs_dir)
    return filename

