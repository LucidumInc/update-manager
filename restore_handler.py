import subprocess
import sys
import time

import fnmatch
import os
import shutil
import tarfile
from docker import DockerClient
from functools import wraps
from io import BytesIO
from loguru import logger

from config_handler import get_db_config, get_mongo_config, get_lucidum_dir, docker_client
from exceptions import AppError


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

    def __init__(self, name: str, filepath: str, client: DockerClient) -> None:
        if filepath and not os.path.isfile(filepath):
            raise AppError(f"'{filepath}' backup file for '{name}' restoring does not exist")
        self.name = name
        self.filepath = filepath
        self.client = client

    def __call__(self):
        raise NotImplementedError

    @staticmethod
    def create_archive(filepath: str):
        tar_stream = BytesIO()
        tar = tarfile.TarFile(fileobj=tar_stream, mode='w')
        with open(filepath, "rb") as f:
            file_data = f.read()
        tarinfo = tarfile.TarInfo(name=os.path.basename(filepath))
        tarinfo.size = len(file_data)
        tarinfo.mtime = time.time()
        tar.addfile(tarinfo, BytesIO(file_data))
        tar.close()
        tar_stream.seek(0)
        return tar_stream


class MySQLRestoreRunner(BaseRestoreRunner):
    container_dest_dir = "/home"

    @log_wrap
    def __call__(self):
        container = self.client.containers.get("mysql")
        tar_stream = self.create_archive(self.filepath)
        success = container.put_archive(self.container_dest_dir, tar_stream)
        if not success:
            raise AppError(f"Putting '{self.filepath}' file to 'mysql' container was failed")
        db_config = get_db_config()
        restore_cmd = f"/bin/bash -c 'mysql --user={{mysql_user}} {{mysql_db}} < {self.container_dest_dir}/{os.path.basename(self.filepath)}'"
        try:
            result = container.exec_run(restore_cmd.format(**db_config), environment={"MYSQL_PWD": db_config["mysql_pwd"]})
            if result.exit_code:
                raise AppError(result.output.decode('utf-8'))
        finally:
            rm_result = container.exec_run(f"rm {self.container_dest_dir}/{os.path.basename(self.filepath)}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))


class MongoRestoreRunner(BaseRestoreRunner):
    container_dest_dir = "/home"

    def __init__(self, name: str, filepath: str, client: DockerClient, web_stop=True) -> None:
        super().__init__(name, filepath, client)
        self._web_stop = web_stop

    @log_wrap
    def __call__(self):
        lucidum_dir = get_lucidum_dir()
        docker_compose_executable = shutil.which("docker-compose")
        if self._web_stop:
            subprocess.run([docker_compose_executable, "stop", self.web_service], cwd=lucidum_dir, check=True)
        container = self.client.containers.get("mongo")
        tar_stream = self.create_archive(self.filepath)
        success = container.put_archive(self.container_dest_dir, tar_stream)
        if not success:
            raise AppError(f"Putting '{self.filepath}' file to 'mongo' container was failed")
        restore_cmd = f"mongorestore -v --username={{mongo_user}} --password={{mongo_pwd}} --authenticationDatabase=test_database --host={{mongo_host}} --port={{mongo_port}} --archive={self.container_dest_dir}/{os.path.basename(self.filepath)} --gzip --db={{mongo_db}} --drop"
        try:
            result = container.exec_run(restore_cmd.format(**get_mongo_config()))
            if result.exit_code:
                raise AppError(result.output.decode('utf-8'))
        finally:
            rm_result = container.exec_run(f"rm {self.container_dest_dir}/{os.path.basename(self.filepath)}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))
            if self._web_stop:
                subprocess.run([docker_compose_executable, "start", self.web_service], cwd=lucidum_dir, check=True)


class LucidumDirRestoreRunner(BaseRestoreRunner):
    mysql_dump_pattern = "mysql_dump_*.sql"
    mongo_dump_pattern = "mongo_dump_*.gz"

    @log_wrap
    def __call__(self):
        lucidum_dir = get_lucidum_dir()
        docker_compose_executable = shutil.which("docker-compose")
        subprocess.run([docker_compose_executable, "stop", self.web_service], cwd=lucidum_dir, check=True)
        mysql_dump_file = mongo_dump_file = None
        restore_cmd = f"sudo tar -xvf {self.filepath} --directory={lucidum_dir}"
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
            MySQLRestoreRunner("mysql", mysql_dump_file, self.client)()
            MongoRestoreRunner("mongo", mongo_dump_file, self.client, web_stop=False)()
        finally:
            subprocess.run([docker_compose_executable, "start", self.web_service], cwd=lucidum_dir, check=True)
            if os.path.isfile(mysql_dump_file):
                os.remove(mysql_dump_file)
            if os.path.isfile(mongo_dump_file):
                os.remove(mongo_dump_file)

    @staticmethod
    def _find_file_by_pattern(_dir, file_pattern):
        files = fnmatch.filter(os.listdir(_dir), file_pattern)
        if not files:
            raise AppError(f"File with '{file_pattern}' pattern was not found in '{_dir}' directory")
        return files[0]


def get_restore_runner(data_to_restore: str, filepath: str):
    if data_to_restore == "mysql":
        return MySQLRestoreRunner(data_to_restore, filepath, docker_client)
    elif data_to_restore == "mongo":
        return MongoRestoreRunner(data_to_restore, filepath, docker_client)
    elif data_to_restore == "lucidum":
        return LucidumDirRestoreRunner(data_to_restore, filepath, docker_client)
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
