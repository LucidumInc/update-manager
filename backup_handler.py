import os
import subprocess
from datetime import datetime

from docker import DockerClient
from loguru import logger

from config_handler import get_db_config, get_mongo_config, get_lucidum_dir, get_backup_dir, get_demo_pwd
from exceptions import AppError


class BaseBackupRunner:
    backup_file_format = None

    def __init__(self, name: str, backup_dir: str = None) -> None:
        self.name = name
        self.backup_dir = backup_dir
        self.datetime_now = datetime.now()

    @property
    def backup_file(self):
        backup_file = self.backup_file_format.format(date=self.datetime_now.strftime('%Y%m%d_%H%M%S'))
        if self.backup_dir is not None:
            backup_file = os.path.join(self.backup_dir, backup_file)
        return backup_file

    def __call__(self):
        raise NotImplementedError


class MySQLBackupRunner(BaseBackupRunner):
    backup_file_format = "mysql_dump_{date}.sql"

    def __init__(self, name: str, client: DockerClient, backup_dir: str = None) -> None:
        super().__init__(name, backup_dir=backup_dir)
        self._client = client

    def __call__(self):
        container = self._client.containers.get("mysql")
        dump_cmd = "mysqldump --user={mysql_user} {mysql_db}"
        db_config = get_db_config()
        logger.info("Dumping data for '{}' into {} file...", self.name, self.backup_file)
        result = container.exec_run(dump_cmd.format(**db_config), environment={"MYSQL_PWD": db_config["mysql_pwd"]})
        if result.exit_code:
            raise AppError(result.output.decode('utf-8'))
        with open(self.backup_file, "wb") as f:
            f.write(result.output)
        logger.info("'{}' backup data is saved to {}", self.name, self.backup_file)
        return self.backup_file


class MongoBackupRunner(BaseBackupRunner):
    backup_file_format = "mongo_dump_{date}.gz"

    def __call__(self):
        dump_cmd = f"mongodump --username={{mongo_user}} --password={{mongo_pwd}} --authenticationDatabase=test_database --host={{mongo_host}} --port={{mongo_port}} --forceTableScan --archive={self.backup_file} --gzip --db={{mongo_db}}"
        logger.info("Dumping data for '{}' into {} file...", self.name, self.backup_file)
        try:
            subprocess.run(dump_cmd.format(**get_mongo_config()).split(), check=True)
        except Exception as e:
            if os.path.isfile(self.backup_file):
                os.remove(self.backup_file)
            raise e
        logger.info("'{}' backup data is saved to {}", self.name, self.backup_file)
        return self.backup_file


class LucidumDirBackupRunner(BaseBackupRunner):
    backup_file_format = "lucidum_{date}.tar.gz"

    def __init__(self, name: str, client: DockerClient, backup_dir: str = None) -> None:
        super().__init__(name, backup_dir=backup_dir)
        self._client = client

    def __call__(self):
        lucidum_dir = get_lucidum_dir()
        mysql_backup_file = MySQLBackupRunner("mysql", self._client, backup_dir=lucidum_dir)()
        mongo_backup_file = MongoBackupRunner("mongo", backup_dir=lucidum_dir)()
        dump_cmd = f"sudo -S tar -czvf {self.backup_file} --exclude=update-manager --directory={lucidum_dir} ."
        logger.info("Dumping data for '{}' into {} file...", self.name, self.backup_file)
        try:
            process = subprocess.Popen(
                dump_cmd.split(),
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                cwd=lucidum_dir
            )
            _, err = process.communicate(f"{get_demo_pwd()}\n")
            if process.returncode:
                if os.path.isfile(self.backup_file):
                    logger.warning(err)
                else:
                    raise AppError(err)
        finally:
            if os.path.isfile(mysql_backup_file):
                os.remove(mysql_backup_file)
            if os.path.isfile(mongo_backup_file):
                os.remove(mongo_backup_file)
        logger.info("'{}' backup data is saved to {}", self.name, self.backup_file)
        return self.backup_file


def get_backup_runner(data_to_backup: str, client: DockerClient):
    if data_to_backup == "mysql":
        return MySQLBackupRunner(data_to_backup, client, backup_dir=get_backup_dir())
    elif data_to_backup == "mongo":
        return MongoBackupRunner(data_to_backup, backup_dir=get_backup_dir())
    elif data_to_backup == "lucidum":
        return LucidumDirBackupRunner(data_to_backup, client, backup_dir=get_backup_dir())
    else:
        raise AppError(f"Cannot backup data for {data_to_backup}")


def backup(data: list):
    try:
        client = DockerClient.from_env()
        backup_runners = [get_backup_runner(d, client) for d in data]
        for backup_runner in backup_runners:
            backup_runner()
    except AppError as e:
        logger.exception(e)
    except Exception:
        logger.exception("Unhandled exception occurred")
