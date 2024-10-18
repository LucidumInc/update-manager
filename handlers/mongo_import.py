import sys

import os
from loguru import logger

from config_handler import get_mongo_config
from docker_service import create_archive, get_docker_container
from exceptions import AppError
from api_handler import MongoDBClient


class MongoImportJsonRunner:
    container_dest_dir = "/bitnami/mongodb"

    def __call__(self, source, destination, drop=False, override=False, upsert_fields='_id'):
        container = get_docker_container("mongo")
        container_filepath = f"{self.container_dest_dir}/{os.path.basename(source)}"
        import_cmd = f"mongoimport --username={{mongo_user}} --password={{mongo_pwd}} --authenticationDatabase=test_database --host={{mongo_host}} --port={{mongo_port}} --db={{mongo_db}} --collection={destination} --file={container_filepath}"
        if drop is True:
            import_cmd += ' --drop'
        elif override is True:
            import_cmd += f' --mode=upsert --upsertFields={upsert_fields}'
        try:
            result = container.exec_run(import_cmd.format(**get_mongo_config()))
            if result.exit_code:
                logger.error(result.output.decode('utf-8'))
        finally:
            rm_result = container.exec_run(f"rm {container_filepath}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))


@logger.catch(onerror=lambda _: sys.exit(1))
def run(source, destination, drop=False, override=False, upsert_fields='_id'):
    if destination.lower() == 'smart_label':
        db_client = MongoDBClient()
        smartlabel_table = db_client.client[db_client._mongo_db][destination]
        d = smartlabel_table.delete_many({'created_by': 'lucidum_vosl'})
        logger.info(f"{d.deleted_count} old VOSL records deleted!")

    import_runner = MongoImportJsonRunner()
    import_runner(source, destination, drop=drop, override=override, upsert_fields=upsert_fields)
