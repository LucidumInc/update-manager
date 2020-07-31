import os
import shutil
import sys

from crontab import CronTab
from loguru import logger

from config_handler import get_lucidum_dir
from exceptions import AppError


def change_permissions_recursive(path, mode):
    for root, dirs, files in os.walk(path):
        for dir_ in dirs:
            os.chmod(os.path.join(root, dir_), mode)
        for file in files:
            os.chmod(os.path.join(root, file), mode)


def create_mongo_directory(base_dir):
    mongo_dir = os.path.join(base_dir, "mongo")
    os.makedirs(os.path.join(mongo_dir, "db"), exist_ok=True)
    change_permissions_recursive(mongo_dir, 0o777)
    return mongo_dir


def create_mysql_directory(base_dir):
    mysql_dir = os.path.join(base_dir, "mysql")
    os.makedirs(os.path.join(mysql_dir, "db"), exist_ok=True)
    config_dir = os.path.join(mysql_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    shutil.copyfile(os.path.join("resources", "mysql_my_custom_cnf"), os.path.join(config_dir, "my_custom.cnf"))
    change_permissions_recursive(mysql_dir, 0o777)
    return mysql_dir


def create_web_directory(base_dir):
    web_dir = os.path.join(base_dir, "web")
    os.makedirs(os.path.join(web_dir, "app", "logs"), exist_ok=True)
    os.makedirs(os.path.join(web_dir, "app", "hostdata"), exist_ok=True)
    change_permissions_recursive(web_dir, 0o777)
    return web_dir


def create_crontab_task_directory(base_dir):
    crontab_task_dir = os.path.join(base_dir, "crontabTask")
    os.makedirs(crontab_task_dir, exist_ok=True)
    shutil.copyfile(os.path.join("resources", "getSysInfo.sh"), os.path.join(crontab_task_dir, "getSysInfo.sh"))
    shutil.copyfile(os.path.join("resources", "sysInfo_lib.py"), os.path.join(crontab_task_dir, "sysInfo_lib.py"))
    change_permissions_recursive(crontab_task_dir, 0o777)
    return crontab_task_dir


def add_cron_job(cron: CronTab, command: str):
    cmd = command.strip()
    if cmd in [job.command for job in cron]:
        raise AppError(f"Command '{cmd}' is already defined as crontab task")
    return cron.new(cmd)


def setup_cron_jobs(jobs):
    cron = CronTab(user=True)
    for time_restriction, command in jobs:
        try:
            job = add_cron_job(cron, command)
        except AppError as e:
            logger.info(e)
            continue
        job.setall(time_restriction)
    cron.write()


def get_cron_jobs(lucidum_dir: str):
    return [
        ("* * * * *", f"{lucidum_dir}/crontabTask/getSysInfo.sh"),
        ("* * * * *", f"sleep 10 ; {lucidum_dir}/crontabTask/getSysInfo.sh"),
        ("* * * * *", f"sleep 20 ; {lucidum_dir}/crontabTask/getSysInfo.sh"),
        ("* * * * *", f"sleep 30 ; {lucidum_dir}/crontabTask/getSysInfo.sh"),
        ("* * * * *", f"sleep 40 ; {lucidum_dir}/crontabTask/getSysInfo.sh"),
        ("* * * * *", f"sleep 50 ; {lucidum_dir}/crontabTask/getSysInfo.sh"),
    ]


@logger.catch(onerror=lambda _: sys.exit(1))
def init():
    lucidum_dir = get_lucidum_dir()
    os.makedirs(lucidum_dir, exist_ok=True)
    shutil.copyfile(os.path.join("resources", "docker-compose_env_file"), os.path.join(lucidum_dir, ".env"))
    shutil.copyfile(os.path.join("resources", "docker-compose_file"), os.path.join(lucidum_dir, "docker-compose.yml"))
    create_mongo_directory(lucidum_dir)
    create_mysql_directory(lucidum_dir)
    create_web_directory(lucidum_dir)
    create_crontab_task_directory(lucidum_dir)
    setup_cron_jobs(get_cron_jobs(lucidum_dir))
