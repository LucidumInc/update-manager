import sys
import requests
import subprocess
import json
import os
from loguru import logger

from config_handler import get_mongo_config
from docker_service import create_archive, get_docker_container
from exceptions import AppError
from api_handler import MongoDBClient


def run_import_cmd(source, destination, drop=False, override=False, upsert_fields=None):
    logger.info("[mongoimport] ===================================================================")
    configs = get_mongo_config()
    is_srv = configs["mongo_host"].startswith("mongodb+srv://")
    # File path depends on execution mode
    if is_srv:
        filepath = f"/usr/lucidum/mongo/db/{source}"   # host path
    else:
        filepath = f"/bitnami/mongodb/{source}"        # container path
    auth_db = "admin" if is_srv else "test_database"
    logger.info(
        f"[mongoimport] Starting import for collection='{destination}' "
        f"source='{source}' srv_mode={is_srv} filepath='{filepath}' auth_db='{auth_db}'"
    )
    # Build the base mongoimport command template
    import_cmd = (
        f"mongoimport "
        f"--username={{mongo_user}} "
        f"--password={{mongo_pwd}} "
        f"--authenticationDatabase={auth_db} "
        f"--host={{mongo_host}} "
        f"--port={{mongo_port}} "
        f"--db={{mongo_db}} "
        f"--collection={destination} "
        f"--file={filepath}"
    )
    if drop:
        import_cmd += " --drop"
        logger.info(f"[mongoimport] Mode: drop existing documents")
    elif override:
        import_cmd += f" --mode=upsert --upsertFields={upsert_fields}"
        logger.info(f"[mongoimport] Mode: upsert override on fields={upsert_fields}")
    else:
        logger.info(f"[mongoimport] Mode: insert only")

    formatted_cmd = import_cmd.format(**configs)
    # --- Branch 1: Mongo Atlas → run via subprocess on host ---
    if is_srv:
        logger.info(f"[mongoimport] Executing on host via subprocess: {formatted_cmd}")
        try:
            cmd_list = formatted_cmd.split()
            subprocess.run(cmd_list, check=True)
            logger.info(f"[mongoimport] Import completed successfully (host subprocess mode)")
        except Exception as e:
            logger.warning(
                f"[mongoimport] FAILED for source='{source}' into '{destination}': {e}"
            )
        finally:
            try:
                os.remove(filepath)
                logger.info(f"[mongoimport] Removed host file '{filepath}'")
            except Exception as e:
                logger.warning(f"[mongoimport] Could not remove host file '{filepath}': {e}")
        return
    # --- Branch 2: Normal host → run inside Docker container ---
    container = get_docker_container("mongo")
    logger.info(f"[mongoimport] Executing inside container: {formatted_cmd}")
    try:
        result = container.exec_run(formatted_cmd)
        if result.exit_code:
            logger.error(
                f"[mongoimport] FAILED inside container (exit={result.exit_code}): "
                f"{result.output.decode('utf-8')}"
            )
        else:
            logger.info(f"[mongoimport] Import completed successfully (container mode)")
    finally:
        rm_result = container.exec_run(f"rm {filepath}", user="root")
        if rm_result.exit_code:
            logger.warning(
                f"[mongoimport] Could not remove container file '{filepath}': "
                f"{rm_result.output.decode('utf-8')}"
            )
        else:
            logger.info(f"[mongoimport] Removed container file '{filepath}'")


class MongoImportJsonRunner:
    container_dest_dir = "/bitnami/mongodb"

    def __call__(self, source, destination, drop=False, override=False, upsert_fields='_id'):
        run_import_cmd(source, destination, drop=False, override=False, upsert_fields='_id')


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
            with open(source_path, 'r', encoding='utf-8') as f:
                import_data = [json.loads(s) for s in f.readlines() if s.strip()]
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
