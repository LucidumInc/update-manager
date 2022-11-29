import sys

import os
from loguru import logger

from config_handler import get_mongo_config
from docker_service import create_archive, get_docker_container
from exceptions import AppError

class QueryUpgradeRunner:
    container_dest_dir = "/bitnami/mongodb"

    def import_json(self, source, destination, drop=False, override=False, upsert_fields='_id'):
        container = get_docker_container("mongo")
        container_filepath = f"{self.container_dest_dir}/{os.path.basename(source)}"
        import_cmd = f"mongoimport --username={{mongo_user}} --password={{mongo_pwd}} --authenticationDatabase=test_database --host={{mongo_host}} --port={{mongo_port}} --db={{mongo_db}} --collection={destination} --file={container_filepath}"
        if drop is True:
            import_cmd += ' --drop'
        elif override is True:
            import_cmd += f' --mode=upsert upsertFields={upsert_fields}'
        try:
            result = container.exec_run(import_cmd.format(**get_mongo_config()))
            if result.exit_code:
                logger.error(result.output.decode('utf-8'))
        finally:
            rm_result = container.exec_run(f"rm {container_filepath}", user='root')
            if rm_result.exit_code:
                logger.warning(rm_result.output.decode('utf-8'))

    def __call__(self):
        self.import_json('postReport.json', 'biQuery_lucidum_report', drop=True)
        self.import_json('postDashboard.json', 'biQuery_lucidum_dashboard', drop=True)
        self.import_json('postDynamicFieldDef.json', 'local_dynamic_field_definition', override=True, upsert_fields='field_name')
        self.import_json('postDynamicFieldDisplay.json', 'field_display_local', override=True, upsert_fields='field_name')
        self.import_json('postSavedQuery.json', 'Query_Builder', override=True, upsert_fields='name')


def _get_upgrade_runner(db):
    if db == "mongo":
        return QueryUpgradeRunner()


@logger.catch(onerror=lambda _: sys.exit(1))
def run():
    import_runner = _get_upgrade_runner("mongo")
    import_runner()
