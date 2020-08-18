import json
import os
import sys
from datetime import datetime
from functools import wraps

from loguru import logger

from config_handler import get_ecr_images

HISTORY_DIR = "history"


def get_history_command_choices():
    if os.path.exists(HISTORY_DIR):
        return os.listdir(HISTORY_DIR)
    return []


def history_command(command, get_history_entries, **write_history_kwargs):
    os.makedirs(HISTORY_DIR, exist_ok=True)

    def _history_command(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with open(os.path.join(HISTORY_DIR, command), "a") as f:
                for entry in get_history_entries(args, kwargs, **write_history_kwargs):
                    f.write(f"{entry}\n")
            return func(*args, **kwargs)
        return wrapper
    return _history_command


def get_install_ecr_entries(command_ags, command_kwargs, **kwargs) -> str:
    get_images = get_ecr_images
    if "get_images" in kwargs:
        get_images = kwargs["get_images"]
    dt = datetime.now()
    for image in get_images():
        if f"{image['name']}:{image['version']}" not in command_kwargs["components"]:
            continue
        entry = {
            "datetime": dt,
            "name": image["name"],
            "version": image["version"],
            "hostPath": image.get("hostPath")
        }
        if "install" in command_kwargs:
            entry["install"] = command_kwargs["install"]
        if "remove" in command_kwargs:
            entry["remove"] = command_kwargs["remove"]
        yield json.dumps(entry, default=str)


@logger.catch(onerror=lambda _: sys.exit(1))
def run(command: str):
    with open(os.path.join(HISTORY_DIR, command)) as f:
        for line in f:
            print(line.strip())
