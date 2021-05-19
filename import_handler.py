import sys

import os
from loguru import logger

from config_handler import get_mongo_config
from docker_service import create_archive, get_docker_container
from exceptions import AppError


class MongoImportRunner:
    container_dest_dir = "/home"

    def __call__(self, source, destination):
        container = get_docker_container("mongo")
        tar_stream = create_archive(source)
        success = container.put_archive(self.container_dest_dir, tar_stream)
        if not success:
            raise AppError(f"Putting '{source}' file to 'mongo' container was failed")
        container_filepath = f"{self.container_dest_dir}/{os.path.basename(source)}"
        import_cmd = f"mongoimport --username={{mongo_user}} --password={{mongo_pwd}} --authenticationDatabase=test_database --host={{mongo_host}} --port={{mongo_port}} --db={{mongo_db}} --collection={destination} --file={container_filepath}"
        try:
            result = container.exec_run(import_cmd.format(**get_mongo_config()))
            if result.exit_code:
                raise AppError(result.output.decode('utf-8'))
        finally:
            rm_result = container.exec_run(f"rm {container_filepath}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))


def _get_import_runner(db):
    if db == "mongo":
        return MongoImportRunner()


@logger.catch(onerror=lambda _: sys.exit(1))
def run(db, source, destination):
    import_runner = _get_import_runner(db)
    import_runner(source, destination)
