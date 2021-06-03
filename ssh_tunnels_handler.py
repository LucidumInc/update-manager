import subprocess

import os
from loguru import logger

from exceptions import AppError

SYSTEMD_UNIT_PATH = os.path.join(os.sep, "etc", "systemd", "system")


def restart_systemctl_service(service_name: str, super_user: bool = False):
    command = f"{'sudo ' if super_user else ''}systemctl restart {service_name}"
    try:
        subprocess.run(command.split(), check=True)
    except Exception as e:
        logger.exception("Error during restart of {} service: {}", service_name, e)
        raise AppError(str(e)) from e


def reload_systemctl_daemon(super_user: bool = False):
    command = f"{'sudo ' if super_user else ''}systemctl daemon-reload"
    try:
        subprocess.run(command.split(), check=True)
    except Exception as e:
        logger.exception("Error during daemon reload: {}", e)
        raise AppError(str(e)) from e


def stop_systemctl_service(service_name: str, super_user: bool = False):
    command = f"{'sudo ' if super_user else ''}systemctl stop {service_name}"
    try:
        subprocess.run(command.split(), check=True)
    except Exception as e:
        logger.exception("Error during stop of {} service: {}", service_name, e)
        raise AppError(str(e)) from e


def disable_systemctl_service(service_name: str, super_user: bool = False):
    command = f"{'sudo ' if super_user else ''}systemctl disable {service_name}"
    try:
        subprocess.run(command.split(), check=True)
    except Exception as e:
        logger.exception("Error during disable of {} service: {}", service_name, e)
        raise AppError(str(e)) from e


class FileEditor:

    def __init__(self, filename: str) -> None:
        self._filename = filename
        self._content = ""

    def __enter__(self):
        with open(self._filename) as f:
            self._content = f.read()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with open(self._filename, mode="w") as f:
            f.write(self._content)

    @property
    def content(self):
        return self._content

    def replace(self, old_: str, new_: str):
        self._content = self._content.replace(old_, new_)


def enable_jumpbox_tunnels(customer_name: str, customer_number: int):
    jumpbox_primary_path = os.path.join(SYSTEMD_UNIT_PATH, "lucidum-jumpbox-primary.service")
    jumpbox_secondary_path = os.path.join(SYSTEMD_UNIT_PATH, "lucidum-jumpbox-secondary.service")
    with FileEditor(jumpbox_primary_path) as editor:
        editor.replace("CUSTOMER_NAME", customer_name)
        editor.replace("CUSTOMER_PORT", str(customer_number))
        jumpbox_primary_content = editor.content
    with FileEditor(jumpbox_secondary_path) as editor:
        editor.replace("CUSTOMER_NAME", customer_name)
        editor.replace("CUSTOMER_PORT", str(customer_number))
        jumpbox_secondary_content = editor.content
    reload_systemctl_daemon(super_user=True)
    restart_systemctl_service("lucidum-jumpbox-primary", super_user=True)
    restart_systemctl_service("lucidum-jumpbox-secondary", super_user=True)
    return jumpbox_primary_content, jumpbox_secondary_content


def disable_jumpbox_tunnels():
    stop_systemctl_service("lucidum-jumpbox-primary", super_user=True)
    stop_systemctl_service("lucidum-jumpbox-secondary", super_user=True)
    disable_systemctl_service("lucidum-jumpbox-primary", super_user=True)
    disable_systemctl_service("lucidum-jumpbox-secondary", super_user=True)
