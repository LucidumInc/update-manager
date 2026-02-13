import sys

import os
from loguru import logger
from handlers.mongo_import import run_import_cmd
from config_handler import get_mongo_config
from docker_service import create_archive, get_docker_container
from exceptions import AppError


class MongoImportRunner:
    def __call__(self, source, destination, drop=False, override=False, upsert_fields=None):
        run_import_cmd(
            source=source,
            destination=destination,
            drop=drop,
            override=override,
            upsert_fields=upsert_fields
        )


def _get_import_runner(db):
    if db == "mongo":
        return MongoImportRunner()


@logger.catch(onerror=lambda _: sys.exit(1))
def run(db, source, destination):
    import_runner = _get_import_runner(db)
    import_runner(source, destination)
