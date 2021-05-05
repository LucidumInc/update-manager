import grp
import platform
import pwd

import boto3
import distro
import os
import psutil
import requests
from psutil._common import bytes2human


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
