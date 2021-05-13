import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import os
from docker import DockerClient
from loguru import logger

from config_handler import get_db_config, get_mongo_config, get_lucidum_dir, get_backup_dir, docker_client
from exceptions import AppError
from file_handler import get_file_handler, LocalFileHandler


class BaseBackupRunner:
    backup_filename_format = None

    def __init__(self, name: str, file_handler, backup_dir: str = None, filepath: str = None) -> None:
        self.name = name
        self.file_handler = file_handler
        self.backup_dir = backup_dir
        if filepath:
            self._validate_file_extension(filepath)
        self._filepath = filepath
        self.datetime_now = datetime.now()
        if self.backup_dir is not None:
            os.makedirs(backup_dir, exist_ok=True)

    @property
    def backup_file(self):
        if self._filepath:
            backup_file = self._filepath
        else:
            backup_file = self.backup_filename_format.format(date=self.datetime_now.strftime('%Y%m%d_%H%M%S'))
            if self.backup_dir is not None:
                backup_file = os.path.join(self.backup_dir, backup_file)
        return backup_file

    def _validate_file_extension(self, filepath):
        file_ext = "".join(Path(self.backup_filename_format).suffixes)
        if filepath and not filepath.endswith(file_ext):
            raise Exception(f"File for '{self.name}' backup should have '{file_ext}' extension")

    def __call__(self):
        raise NotImplementedError


class MySQLBackupRunner(BaseBackupRunner):
    backup_filename_format = "mysql_dump_{date}.sql"

    def __init__(
            self, name: str, file_handler, client: DockerClient, backup_dir: str = None, filepath: str = None
    ) -> None:
        super().__init__(name, file_handler, backup_dir=backup_dir, filepath=filepath)
        self._client = client

    def __call__(self):
        container = self._client.containers.get("mysql")
        dump_cmd = "mysqldump --user={mysql_user} {mysql_db}"
        db_config = get_db_config()
        logger.info("Dumping data for '{}' into {} file...", self.name, self.backup_file)
        result = container.exec_run(dump_cmd.format(**db_config), environment={"MYSQL_PWD": db_config["mysql_pwd"]})
        if result.exit_code:
            raise AppError(result.output.decode('utf-8'))
        self.file_handler.write(self.backup_file, result.output)
        logger.info("'{}' backup data is saved to {}", self.name, self.backup_file)
        return self.backup_file


class MongoBackupRunner(BaseBackupRunner):
    backup_filename_format = "mongo_dump_{date}.gz"
    container_dir = "/bitnami/mongodb"
    host_dir = "{}/mongo/db"

    def __init__(
            self, name: str, file_handler, client: DockerClient, backup_dir: str = None, filepath: str = None
    ) -> None:
        super().__init__(name, file_handler, backup_dir=backup_dir, filepath=filepath)
        self._client = client

    def __call__(self):
        container = self._client.containers.get("mongo")
        filename = f"{str(uuid.uuid4())}_mongo_dump.gz"
        dump_cmd = f"mongodump --username={{mongo_user}} --password={{mongo_pwd}} --authenticationDatabase=test_database --host={{mongo_host}} --port={{mongo_port}} --forceTableScan --archive={self.container_dir}/{filename} --gzip --db={{mongo_db}}"
        logger.info("Dumping data for '{}' into {} file...", self.name, self.backup_file)
        try:
            result = container.exec_run(dump_cmd.format(**get_mongo_config()))
            if result.exit_code:
                raise AppError(result.output.decode('utf-8'))
            self.file_handler.copy_file(
                os.path.join(self.host_dir.format(get_lucidum_dir()), filename), self.backup_file
            )
        finally:
            rm_result = container.exec_run(f"rm {self.container_dir}/{filename}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))
        logger.info("'{}' backup data is saved to {}", self.name, self.backup_file)
        return self.backup_file


class LucidumDirBackupRunner(BaseBackupRunner):
    backup_filename_format = "lucidum_{date}.tar.gz"
    _items_to_exclude = [
        "update-manager",
        "airflow_venv",
        "backup",
        "mongo",
        "mysql",
        "web",
        "crontabTask",
        "airflow/logs/*",
        "airflow/*.pid",
        "__pycache__",
        "venv",
        "virtualenv",
    ]

    def __init__(
            self, name: str, file_handler, client: DockerClient, backup_dir: str = None, filepath: str = None
    ) -> None:
        super().__init__(name, file_handler, backup_dir=backup_dir, filepath=filepath)
        self._client = client

    def __call__(self):
        lucidum_dir = get_lucidum_dir()
        local_file_handler = LocalFileHandler()
        mysql_backup_file = MySQLBackupRunner("mysql", local_file_handler, self._client, backup_dir=lucidum_dir)()
        mongo_backup_file = MongoBackupRunner("mongo", local_file_handler, self._client, backup_dir=lucidum_dir)()
        excludes = " ".join(f"--exclude={f}" for f in self._items_to_exclude)
        backup_filepath = os.path.join(self.backup_dir, f"{str(uuid.uuid4())}_lucidum.tar.gz")
        dump_cmd = f"sudo tar -czvf {backup_filepath} {excludes} --directory={lucidum_dir} ."
        logger.info("Dumping data for '{}' into {} file...", self.name, self.backup_file)
        try:
            subprocess.run(dump_cmd.split(), check=True)
            self.file_handler.copy_file(backup_filepath, self.backup_file)
        finally:
            if os.path.isfile(mysql_backup_file):
                os.remove(mysql_backup_file)
            if os.path.isfile(mongo_backup_file):
                os.remove(mongo_backup_file)
            if os.path.isfile(backup_filepath):
                os.remove(backup_filepath)
        logger.info("'{}' backup data is saved to {}", self.name, self.backup_file)
        return self.backup_file


def get_backup_runner(data_to_backup: str, filepath: str = None):
    backup_dir = get_backup_dir()
    file_handler = get_file_handler(filepath) if filepath is not None else LocalFileHandler()
    if data_to_backup == "mysql":
        return MySQLBackupRunner(data_to_backup, file_handler, docker_client, backup_dir=backup_dir, filepath=filepath)
    elif data_to_backup == "mongo":
        return MongoBackupRunner(data_to_backup, file_handler, docker_client, backup_dir=backup_dir, filepath=filepath)
    elif data_to_backup == "lucidum":
        return LucidumDirBackupRunner(
            data_to_backup, file_handler, docker_client, backup_dir=backup_dir, filepath=filepath
        )
    else:
        raise AppError(f"Cannot backup data for {data_to_backup}")


@logger.catch(onerror=lambda _: sys.exit(1))
def backup(data: list, filepath: str):
    try:
        backup_runners = [get_backup_runner(d, filepath) for d in data]
        for backup_runner in backup_runners:
            backup_runner()
    except AppError as e:
        logger.exception(e)
        raise e
