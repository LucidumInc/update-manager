import subprocess
import sys
import uuid

import fnmatch
import os
import shutil
from functools import wraps
from loguru import logger

from config_handler import get_db_config, get_mongo_config, get_lucidum_dir, get_backup_dir
from docker_service import create_archive, get_docker_container
from exceptions import AppError
from file_handler import get_file_handler, LocalFileHandler
from handlers.mongo_backup_restore import run_mongo_backup_or_restore


def log_wrap(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        self_arg = args[0]
        logger.info("Restoring data for '{}' from '{}' file...", self_arg.name, self_arg.filepath)
        result = func(*args, **kwargs)
        logger.info("'{}' data was restored from '{}' file", self_arg.name, self_arg.filepath)
        return result
    return wrapper


class BaseRestoreRunner:
    web_service = "web"

    def __init__(self, name: str, filepath: str, file_handler) -> None:
        self.name = name
        self.filepath = filepath
        self.file_handler = file_handler

    def get_backup_filepath(self) -> str:
        backup_dir = get_backup_dir()
        os.makedirs(backup_dir, exist_ok=True)
        backup_filepath = os.path.join(backup_dir, str(uuid.uuid4()))
        self.file_handler.place_file(self.filepath, backup_filepath)
        return backup_filepath

    def __call__(self):
        raise NotImplementedError


class MySQLRestoreRunner(BaseRestoreRunner):
    container_dest_dir = "/home"

    @log_wrap
    def __call__(self):
        container = get_docker_container("mysql")
        local_filepath = self.get_backup_filepath()
        tar_stream = create_archive(local_filepath)
        success = container.put_archive(self.container_dest_dir, tar_stream)
        if not success:
            raise AppError(f"Putting '{self.filepath}' file to 'mysql' container was failed")
        db_config = get_db_config()
        restore_cmd = f"/bin/bash -c 'mysql --user={{mysql_user}} {{mysql_db}} < {self.container_dest_dir}/{os.path.basename(local_filepath)}'"
        try:
            result = container.exec_run(restore_cmd.format(**db_config), environment={"MYSQL_PWD": db_config["mysql_pwd"]})
            if result.exit_code:
                raise AppError(result.output.decode('utf-8'))
        finally:
            rm_result = container.exec_run(f"rm {self.container_dest_dir}/{os.path.basename(local_filepath)}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))
            if os.path.isfile(local_filepath):
                os.remove(local_filepath)


class MongoRestoreRunner(BaseRestoreRunner):
    container_dest_dir = "/home"

    def __init__(self, name: str, filepath: str, file_handler, web_stop=True) -> None:
        super().__init__(name, filepath, file_handler)
        self._web_stop = web_stop

    @log_wrap
    def __call__(self):
        run_mongo_backup_or_restore(
            mode="restore",
            backup_file=self.get_backup_filepath(),
            stop_web=self._web_stop,
            web_service=self.web_service,
            name=self.name
        )


class LucidumDirRestoreRunner(BaseRestoreRunner):
    mysql_dump_pattern = "mysql_dump_*.sql"
    mongo_dump_pattern = "mongo_dump_*.gz"

    @log_wrap
    def __call__(self):
        lucidum_dir = get_lucidum_dir()
        docker_compose_executable = shutil.which("docker")
        subprocess.run([docker_compose_executable, "compose", "stop", self.web_service], cwd=lucidum_dir, check=True)
        mysql_dump_file = mongo_dump_file = None
        local_filepath = self.get_backup_filepath()
        restore_cmd = f"sudo tar -xvf {local_filepath} --directory={lucidum_dir}"
        try:
            try:
                subprocess.run(restore_cmd.split(), check=True)
            except Exception as error:
                try:
                    mysql_dump_file = f"{lucidum_dir}/{self._find_file_by_pattern(lucidum_dir, self.mysql_dump_pattern)}"
                    mongo_dump_file = f"{lucidum_dir}/{self._find_file_by_pattern(lucidum_dir, self.mongo_dump_pattern)}"
                except AppError as e:
                    logger.warning(e)
                raise error
            mysql_dump_file = f"{lucidum_dir}/{self._find_file_by_pattern(lucidum_dir, self.mysql_dump_pattern)}"
            mongo_dump_file = f"{lucidum_dir}/{self._find_file_by_pattern(lucidum_dir, self.mongo_dump_pattern)}"
            local_file_handler = LocalFileHandler()
            MySQLRestoreRunner("mysql", mysql_dump_file, local_file_handler)()
            MongoRestoreRunner("mongo", mongo_dump_file, local_file_handler, web_stop=False)()
        finally:
            subprocess.run([docker_compose_executable, "start", self.web_service], cwd=lucidum_dir, check=True)
            if os.path.isfile(mysql_dump_file):
                os.remove(mysql_dump_file)
            if os.path.isfile(mongo_dump_file):
                os.remove(mongo_dump_file)
            if os.path.isfile(local_filepath):
                os.remove(local_filepath)

    @staticmethod
    def _find_file_by_pattern(_dir, file_pattern):
        files = fnmatch.filter(os.listdir(_dir), file_pattern)
        if not files:
            raise AppError(f"File with '{file_pattern}' pattern was not found in '{_dir}' directory")
        return files[0]


def get_restore_runner(data_to_restore: str, filepath: str):
    file_handler = get_file_handler(filepath)
    if data_to_restore == "mysql":
        return MySQLRestoreRunner(data_to_restore, filepath, file_handler)
    elif data_to_restore == "mongo":
        return MongoRestoreRunner(data_to_restore, filepath, file_handler)
    elif data_to_restore == "lucidum":
        return LucidumDirRestoreRunner(data_to_restore, filepath, file_handler)
    else:
        raise AppError(f"Cannot restore data for {data_to_restore}")


def restore(data: list):
    results = []
    for name, filepath in data:
        try:
            get_restore_runner(name, filepath)()
            results.append((name, 'success', 'Restored successfully'))
        except AppError as e:
            logger.exception(e)
            results.append((name, 'failed', str(e)))
        except Exception as e:
            logger.exception("Unhandled exception occurred")
            results.append((name, 'failed', str(e)))
    messages = [f"{name} ({status}): {message}" for name, status, message in results]
    logger.info("Restore process is finished:\n{}", "\n".join(messages))
    if any(status == "failed" for _, status, _ in results):
        sys.exit(1)
