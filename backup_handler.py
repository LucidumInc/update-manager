import subprocess
import sys
import uuid
from datetime import datetime

import os
from loguru import logger

from config_handler import get_db_config, get_mongo_config, get_lucidum_dir, get_backup_dir
from docker_service import get_docker_container
from exceptions import AppError
from file_handler import get_file_handler, LocalFileHandler
from handlers.mongo_backup_restore import run_mongo_backup_or_restore


class BaseBackupRunner:
    backup_filename_format = None

    def __init__(self, name: str, file_handler, backup_dir: str = None, path: str = None) -> None:
        self.name = name
        self.file_handler = file_handler
        self.backup_dir = backup_dir or "/usr/lucidum/backup"
        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)
        self._path = path
        self.datetime_now = datetime.now()

    @property
    def backup_file(self):
        backup_file = self.backup_filename_format.format(date=self.datetime_now.strftime('%Y%m%d_%H%M%S'))
        if self._path:
            backup_file = self.file_handler.get_file_path(self._path, backup_file)
        else:
            if self.backup_dir is not None:
                backup_file = os.path.join(self.backup_dir, backup_file)
        return backup_file

    def __call__(self):
        raise NotImplementedError


class MySQLBackupRunner(BaseBackupRunner):
    backup_filename_format = "mysql_dump_{date}.sql"

    def __call__(self):
        container = get_docker_container("mysql")
        dump_cmd = "mysqldump --no-tablespaces --user={mysql_user} {mysql_db}"
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
        self,
        name: str,
        file_handler,
        backup_dir: str = None,
        path: str = None,
        collection: str = None,
        exclude_collections: list = None
    ) -> None:
        super().__init__(name, file_handler, backup_dir, path)
        self.collection = collection
        self.exclude_collections = exclude_collections

    def __call__(self):
        return run_mongo_backup_or_restore(
            mode="backup",
            backup_file=self.backup_file,
            collection=self.collection,
            exclude_collections=self.exclude_collections,
            force_table_scan=True,
            stop_web=False,
            web_service=None,
            name=self.name,
            host_dir=self.host_dir.format(get_lucidum_dir()),
            file_handler=self.file_handler
        )


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
        "postgres"
    ]

    def __call__(self):
        lucidum_dir = get_lucidum_dir()
        local_file_handler = LocalFileHandler()
        mysql_backup_file = MySQLBackupRunner("mysql", local_file_handler, backup_dir=lucidum_dir)()
        mongo_backup_file = MongoBackupRunner("mongo", local_file_handler, backup_dir=lucidum_dir)()
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


def get_backup_runner(
    data_to_backup: str, filepath: str = None, collection: str = None, exclude_collections: list = None
):
    backup_dir = get_backup_dir()
    file_handler = get_file_handler(filepath) if filepath is not None else LocalFileHandler()
    if data_to_backup == "mysql":
        return MySQLBackupRunner(data_to_backup, file_handler, backup_dir=backup_dir, path=filepath)
    elif data_to_backup == "mongo":
        return MongoBackupRunner(
            data_to_backup,
            file_handler,
            backup_dir=backup_dir,
            path=filepath,
            collection=collection,
            exclude_collections=exclude_collections
        )
    elif data_to_backup == "lucidum":
        return LucidumDirBackupRunner(
            data_to_backup, file_handler, backup_dir=backup_dir, path=filepath
        )
    else:
        raise AppError(f"Cannot backup data for {data_to_backup}")


@logger.catch(onerror=lambda _: sys.exit(1))
def backup(data: list, filepath: str, collection: str = None, exclude_collections: list = None):
    try:
        backup_runners = [get_backup_runner(d, filepath, collection, exclude_collections) for d in data]
        for backup_runner in backup_runners:
            backup_runner()
    except AppError as e:
        logger.exception(e)
        raise e
