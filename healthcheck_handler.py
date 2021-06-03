import grp
import platform
import pwd
import subprocess
from datetime import datetime, timezone

import boto3
import distro
import os
import psutil
import requests
from dateutil import parser as dateutil_parser, relativedelta
from loguru import logger
from psutil._common import bytes2human

from config_handler import get_aws_config, get_ecr_client
from docker_service import list_docker_containers, get_container_stats
from exceptions import AppError


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
    result = {"status": "OK"}
    try:
        response = requests.get("https://localhost:443/CMDB/api/management/health", verify=False)
        response.raise_for_status()
        result.update(response.json())
    except requests.RequestException as e:
        logger.exception("Error when trying to get UI health: {}?!", e)
        result["status"] = "FAILED"
        result["message"] = str(e)

    return result


def check_airflow_health() -> dict:
    result = {"status": "OK"}
    try:
        response = requests.get("http://localhost:9080/health")
        response.raise_for_status()
        result.update(response.json())
    except requests.RequestException as e:
        logger.exception("Error when trying to get Airflow health: {}?!", e)
        result["status"] = "FAILED"
        result["message"] = str(e)

    return result


def get_aws_credentials() -> dict:
    session = boto3.Session()
    credentials = session.get_credentials()
    credentials = credentials.get_frozen_credentials()
    attributes = ["access_key", "secret_key"]
    return {
        attribute: getattr(credentials, attribute) for attribute in attributes
    }


def check_cron_health() -> dict:
    result = {"status": "OK"}
    command = "systemctl is-active cron"
    try:
        subprocess.run(command.split(), check=True)
    except Exception as e:
        logger.exception("Error during getting status of cron service: {}", e)
        result["status"] = "FAILED"
        result["message"] = str(e)

    return result


def get_systemctl_service_status(service_name: str, super_user: bool = False):
    command = f"{'sudo ' if super_user else ''}systemctl is-active {service_name}"
    try:
        result = subprocess.run(command.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(e)
        output = e.stdout
    return output.decode().strip()


def get_journalctl_service_logs(service_name: str):
    command = f"journalctl -u {service_name} -n 50"
    try:
        result = subprocess.run(command.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(e)
        output = e.stdout
    return output.decode().strip().splitlines()


def get_journalctl_service_pid(service_name: str):
    command = f"systemctl show --property MainPID --value {service_name}"
    try:
        result = subprocess.run(command.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(e)
        output = e.stdout
    return int(output.decode().strip())


def get_system_process_by_pid(pid: int):
    command = f"ps -p {pid} -fww"
    try:
        result = subprocess.run(command.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(e)
        output = e.stdout
    return output.decode().strip().splitlines()


class BaseInfoCollector:
    name = None

    def __call__(self):
        raise NotImplementedError


class SystemInfoCollector(BaseInfoCollector):
    name = "system"

    def __call__(self):
        raise NotImplementedError


class CurrentUserInfoCollector(SystemInfoCollector):
    name = "user"

    def __call__(self):
        user = get_current_user()
        return user["pw_name"]


class CurrentUserGroupsInfoCollector(SystemInfoCollector):
    name = "user_groups"

    def __call__(self):
        user = get_current_user()
        return [group["gr_name"] for group in get_user_groups(user)]


class OSInfoCollector(SystemInfoCollector):
    name = "os"

    def __call__(self):
        data = get_platform_information()
        return f"{data['dist']['name']} {data['dist']['version']}"


class MemoryUsageInfoCollector(SystemInfoCollector):
    name = "memory"

    def __call__(self):
        memory = get_memory_usage()
        return memory["total"]


class DiskUsageInfoCollector(SystemInfoCollector):
    name = "disk"

    def __call__(self):
        disk = get_disk_usage("/")
        return disk["total"]


class CPUUsageInfoCollector(SystemInfoCollector):
    name = "cpu_cores"

    def __call__(self):
        return get_cpu_count()


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

    _not_available = "N/A"

    def __call__(self):
        result = {"status": "OK"}
        access_key, secret_key = get_aws_config()
        try:
            ecr_client = get_ecr_client(access_key, secret_key)
            ecr_client.get_repositories()
        except Exception as e:
            logger.exception("Error during getting aws credentials: {}", e)
            result["status"] = "FAILED"
            result["message"] = str(e)

        result.update({
            "access_key": generate_secret_string(access_key) if access_key else self._not_available,
            "secret_key": generate_secret_string(secret_key) if secret_key else self._not_available,
        })

        return result


class ECRComponentsInfoCollector(BaseInfoCollector):
    name = "containers"

    def __call__(self):
        result = {"status": "OK"}
        containers = []
        try:
            for container in list_docker_containers():
                stats = get_container_stats(container.id, stream=False)
                cpu_percent = self._calculate_cpu_usage_percentage(stats["cpu_stats"], stats["precpu_stats"])
                started_at = dateutil_parser.isoparse(container.attrs["State"]["StartedAt"])
                diff = relativedelta.relativedelta(datetime.now(tz=timezone.utc), started_at)
                containers.append({
                    "name": container.name,
                    "image": container.image.tags[0] if container.image.tags else "",
                    "container_id": container.short_id,
                    "cpu": f"{cpu_percent:.2f}%",
                    "memory": bytes2human(stats["memory_stats"]["usage"]),
                    "pid": container.attrs["State"]["Pid"],
                    "status": f"Up {diff.hours} hours"
                })
            if not containers:
                result["status"] = "FAILED"
                result["message"] = "No containers"
            else:
                result["data"] = containers
        except Exception as e:
            logger.exception("Error during getting docker containers: {}", e)
            result["status"] = "FAILED"
            result["message"] = str(e)

        return result

    def _calculate_cpu_usage_percentage(self, cpu_stats, precpu_stats):
        cpu_count = len(cpu_stats["cpu_usage"]["percpu_usage"])
        cpu_percent = 0.0
        cpu_delta = float(cpu_stats["cpu_usage"]["total_usage"]) - float(precpu_stats["cpu_usage"]["total_usage"])
        system_delta = float(cpu_stats["system_cpu_usage"]) - float(precpu_stats["system_cpu_usage"])
        if system_delta > 0.0:
            cpu_percent = cpu_delta / system_delta * 100.0 * cpu_count
        return cpu_percent


class SSHTunnelsInfoCollector(BaseInfoCollector):
    name = "ssh_tunnels"

    def __call__(self):
        result = {"status": "OK"}
        statuses = []
        services = ["lucidum-jumpbox-primary", "lucidum-jumpbox-secondary"]
        for service in services:
            pid = get_journalctl_service_pid(service)
            status = get_systemctl_service_status(service)
            service_status = {
                "status": status,
                "logs": get_journalctl_service_logs(service),
                "process": get_system_process_by_pid(pid),
            }
            statuses.append(status)
            result[service] = service_status

        if all(status == "inactive" for status in statuses):
            result["status"] = "FAILED"
            result["message"] = "SSH tunnels are inactive"

        return result


def _build_health_info_obj(collector, result: dict = None):
    if result is None:
        result = {}

    subclasses = collector.__subclasses__()
    if not subclasses:
        collect_health_status = collector()
        result[collector.name] = collect_health_status()
    else:
        if collector.name:
            result[collector.name] = {"status": "OK"}
        try:
            for kls in subclasses:
                _build_health_info_obj(kls, result[collector.name] if collector.name in result else result)
        except Exception as e:
            if collector.name:
                result[collector.name]["status"] = "FAILED"
                result[collector.name]["message"] = str(e)


def get_health_information(category: str = None):
    result = {}
    collector = BaseInfoCollector
    if category:
        for kls in BaseInfoCollector.__subclasses__():
            if kls.name == category:
                collector = kls
                break
        else:
            raise AppError(f"No such category: {category}")
    _build_health_info_obj(collector, result)
    return result
