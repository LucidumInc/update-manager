import sys
import requests
import json
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
def run(source, destination, drop=False, override=False, upsert_fields='_id', cleanup=True):
    db_client = MongoDBClient()
    destination_lower = destination.lower()
    db = db_client.client[db_client._mongo_db]
    # Optional cleanup for smart_label or query_builder tables
    if cleanup is True and destination_lower in ['smart_label', 'query_builder']:
        target_table = db[destination]
        field_display_table = db['field_display_local']
        vosl_list = list(target_table.find({'created_by': 'lucidum_vosl'}))
        # For smart labels, also need to clean up the field display local table
        if destination_lower == 'smart_label':
            for vosl in vosl_list:
                field_display_table.delete_many({'field_name': vosl['field_name']})
        # Handle override logic with sent_to_luci preservation
        if destination_lower == 'query_builder':
            # Load import data
            source_path = f"/usr/lucidum/mongo/db/{source}"
            with open(source_path) as f:
                import_data = [json.loads(line) for line in f if line.strip()]
            updated_lines = []
            for item in import_data:
                filter_criteria = {f: item.get(f) for f in upsert_fields.split(',')}
                existing = target_table.find_one(filter_criteria)
                item['sent_to_luci'] = existing.get(
                    'sent_to_luci') if existing and existing.get('sent_to_luci') is not None else True
                updated_lines.append(json.dumps(item, ensure_ascii=False) + '\n')
            with open(source_path, 'w', encoding='utf-8') as f:
                f.writelines(updated_lines)
            logger.info(f"{destination}: {len(updated_lines)} records updated with sent_to_luci preservation")

        d = target_table.delete_many({'created_by': 'lucidum_vosl'})
        logger.info(f"{destination}: {d.deleted_count} old value-oriented records deleted!")

    import_runner = MongoImportJsonRunner()
    import_runner(source, destination, drop=drop, override=override, upsert_fields=upsert_fields)

    # populate luci fields
    # if destination.lower() == 'smart_label':
    #    resp = requests.get("https://localhost/CMDB/api/internal/llm/fields/populate", verify=False, timeout=30)
    #    logger.info(resp.text)
