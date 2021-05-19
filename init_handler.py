import os
import shutil
import sys

from crontab import CronTab
from loguru import logger

from config_handler import get_lucidum_dir
from exceptions import AppError


def change_permissions_recursive(path, mode):
    os.chmod(path, mode)
    for root, dirs, files in os.walk(path):
        for dir_ in dirs:
            os.chmod(os.path.join(root, dir_), mode)
        for file in files:
            os.chmod(os.path.join(root, file), mode)


def create_directory(dir_):
    if not os.path.exists(dir_):
        os.makedirs(dir_)
        logger.info("Created directory: {}", dir_)
        return True

    logger.info("Directory exists: {}", dir_)
    return False


def copy_file(from_, to, force=False):
    if os.path.exists(to):
        if force:
            shutil.copyfile(from_, to)
            logger.info("Copied {} file to {} file", from_, to)
        else:
            logger.info("File exists: {}", to)
    else:
        shutil.copyfile(from_, to)
        logger.info("Copied {} file to {} file", from_, to)


def create_mongo_directory(base_dir):
    mongo_dir = os.path.join(base_dir, "mongo")
    created = create_directory(os.path.join(mongo_dir, "db"))
    if created:
        change_permissions_recursive(mongo_dir, 0o777)
    return mongo_dir


def create_mysql_directory(base_dir):
    mysql_dir = os.path.join(base_dir, "mysql")
    created = create_directory(mysql_dir)
    create_directory(os.path.join(mysql_dir, "db"))
    config_dir = os.path.join(mysql_dir, "config")
    create_directory(config_dir)
    copy_file(os.path.join("resources", "mysql_my_custom_cnf"), os.path.join(config_dir, "my_custom.cnf"))
    if created:
        change_permissions_recursive(mysql_dir, 0o777)
    return mysql_dir


def create_web_directory(base_dir):
    web_dir = os.path.join(base_dir, "web")
    created = create_directory(web_dir)
    create_directory(os.path.join(web_dir, "app", "logs"))
    hostdata_dir = os.path.join(web_dir, "app", "hostdata")
    create_directory(hostdata_dir)
    conf_dir = os.path.join(web_dir, "app", "conf")
    create_directory(conf_dir)
    copy_file(os.path.join("resources", "server.pem"), os.path.join(hostdata_dir, "server.pem"))
    copy_file(os.path.join("resources", "server_private.pem"), os.path.join(hostdata_dir, "server_private.pem"))
    copy_file(os.path.join("resources", "server.xml"), os.path.join(conf_dir, "server.xml"))
    copy_file(os.path.join("resources", "web.xml"), os.path.join(conf_dir, "web.xml"))
    if created:
        change_permissions_recursive(web_dir, 0o777)
    return web_dir


def create_crontab_task_directory(base_dir):
    crontab_task_dir = os.path.join(base_dir, "crontabTask")
    created = create_directory(crontab_task_dir)
    copy_file(os.path.join("resources", "getSysInfo.sh"), os.path.join(crontab_task_dir, "getSysInfo.sh"))
    copy_file(os.path.join("resources", "sysInfo_lib.py"), os.path.join(crontab_task_dir, "sysInfo_lib.py"))
    if created:
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
            logger.warning(e)
            continue
        job.setall(time_restriction)
        logger.info("Created cron job: {} {}", time_restriction, command)
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
    logger.info("Lucidum directory: {}", lucidum_dir)
    create_directory(lucidum_dir)
    create_mongo_directory(lucidum_dir)
    create_mysql_directory(lucidum_dir)
    create_web_directory(lucidum_dir)
    create_crontab_task_directory(lucidum_dir)
    logger.info("Setting up cron jobs...")
    setup_cron_jobs(get_cron_jobs(lucidum_dir))
