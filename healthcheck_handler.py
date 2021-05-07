import grp
import platform
import pwd
import subprocess

import boto3
import distro
import os
import psutil
import requests
from loguru import logger
from psutil._common import bytes2human

from install_handler import get_ecr_to_local_components_conjunction


def get_current_user() -> dict:
    user = pwd.getpwuid(os.getuid())
    attributes = ["pw_name", "pw_passwd", "pw_uid", "pw_gid", "pw_gecos", "pw_dir", "pw_shell"]
    return {attribute: getattr(user, attribute) for attribute in attributes}


def get_user_groups(user: dict) -> list:
    attributes = ["gr_name", "gr_gid"]
    groups = []
    for g in grp.getgrall():
        if user["pw_name"] not in g.gr_mem:
            continue
        groups.append({attribute: getattr(g, attribute) for attribute in attributes})
    user_group = grp.getgrgid(user["pw_gid"])
    groups.append({attribute: getattr(user_group, attribute) for attribute in attributes})
    return groups


def get_platform_information() -> dict:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "release": platform.release(),
        "version": platform.version(),
        "platform": platform.platform(),
        "dist": {
            **distro.info(),
            "name": distro.name(),
        }
    }


def get_memory_usage() -> dict:
    data = psutil.virtual_memory()
    memory = {}
    for name in data._fields:
        value = getattr(data, name)
        if name != "percent":
            value = bytes2human(value)
        memory[name] = value
    return memory


def get_disk_usage(path: str) -> dict:
    data = psutil.disk_usage(path)
    disk = {}
    for name in data._fields:
        value = getattr(data, name)
        if name != "percent":
            value = bytes2human(value)
        disk[name] = value
    return disk


def get_cpu_count(logical: bool = False) -> int:
    return psutil.cpu_count(logical)


def check_ui_health() -> dict:
    response = requests.get("https://localhost:443/CMDB/api/management/health", verify=False)
    return response.json()


def check_airflow_health() -> dict:
    response = requests.get("http://localhost:9080/health")
    return response.json()


def get_aws_credentials() -> dict:
    session = boto3.Session()
    credentials = session.get_credentials()
    credentials = credentials.get_frozen_credentials()
    attributes = ["access_key", "secret_key"]
    return {
        attribute: getattr(credentials, attribute) for attribute in attributes
    }


def check_cron_health() -> dict:
    status = "active"
    command = "systemctl is-active cron"
    try:
        subprocess.run(command.split(), check=True)
    except Exception as e:
        status = "inactive"
        logger.exception("Error during getting status of cron service: {}", e)

    return {
        "status": status
    }


class BaseInfoCollector:
    name = None

    def __call__(self):
        raise NotImplementedError


class CurrentUserInfoCollector(BaseInfoCollector):
    name = "user"

    def __call__(self):
        user = get_current_user()
        return user["pw_name"]


class CurrentUserGroupsInfoCollector(BaseInfoCollector):
    name = "user_groups"

    def __call__(self):
        user = get_current_user()
        return [group["gr_name"] for group in get_user_groups(user)]


class OSInfoCollector(BaseInfoCollector):
    name = "os"

    def __call__(self):
        data = get_platform_information()
        return f"{data['dist']['name']} {data['dist']['version']}"


class MemoryUsageInfoCollector(BaseInfoCollector):
    name = "memory"

    def __call__(self):
        memory = get_memory_usage()
        return {"total": memory["total"]}


class DiskUsageInfoCollector(BaseInfoCollector):
    name = "disk"

    def __call__(self):
        disk = get_disk_usage("/")
        return {"total": disk["total"]}


class CPUUsageInfoCollector(BaseInfoCollector):
    name = "cpu"

    def __call__(self):
        return {"cores": get_cpu_count()}


class UIInfoCollector(BaseInfoCollector):
    name = "ui"

    def __call__(self):
        return check_ui_health()


class AirflowInfoCollector(BaseInfoCollector):
    name = "airflow"

    def __call__(self):
        return check_airflow_health()


class CronServiceInfoCollector(BaseInfoCollector):
    name = "cron"

    def __call__(self):
        return check_cron_health()


def generate_secret_string(value: str, last_visible: int = 4) -> str:
    return f"{'*' * (len(value) - last_visible)}{value[-last_visible:]}"


class AWSCredentialsInfoCollector(BaseInfoCollector):
    name = "aws"

    def __call__(self):
        aws = get_aws_credentials()
        return {
            "access_key": generate_secret_string(aws["access_key"]),
            "secret_key": generate_secret_string(aws["secret_key"]),
        }


class ECRComponentsInfoCollector(BaseInfoCollector):
    name = "components"

    def __call__(self):
        components = get_ecr_to_local_components_conjunction()
        return {
            "status": "OK" if components else "FAILED"
        }


def get_health_information():
    result = {}
    for kls in BaseInfoCollector.__subclasses__():
        collect_health_status = kls()
        result[kls.name] = collect_health_status()
    return result
