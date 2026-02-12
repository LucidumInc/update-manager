import sys
import requests
import subprocess
import json
import os
import shlex
from loguru import logger

from config_handler import get_mongo_config
from docker_service import create_archive, get_docker_container
from exceptions import AppError
from api_handler import MongoDBClient


def run_import_cmd(source, destination, drop=False, override=False, upsert_fields=None):
    """
    Run a mongoimport operation for a given source file into a target collection.

    This unified version always executes mongoimport on the host, regardless of
    whether the MongoDB connection uses an SRV URI (Atlas) or a standard host:port
    connection (local/replica set). Both modes use a consistent --uri-based import.

    Parameters
    ----------
    source : str
        The filename to import (JSON/CSV) already placed in /usr/lucidum/mongo/db/.
    destination : str
        The MongoDB collection name to import into.
    drop : bool
        If True, drop the collection before import.
    override : bool
        If True, perform an upsert import using the provided upsert_fields.
    upsert_fields : str
        Comma-separated list of fields used for upsert matching.
    """
    logger.info("[mongoimport] ===================================================================")
    configs = get_mongo_config()
    is_srv = configs["mongo_host"].startswith("mongodb+srv://")
    filepath = f"/usr/lucidum/mongo/db/{source}"
    logger.info(
        f"[mongoimport] Starting import for collection='{destination}' "
        f"source='{source}' srv_mode={is_srv} filepath='{filepath}'"
    )
    mongo_user = configs["mongo_user"]
    mongo_pwd = configs["mongo_pwd"]
    mongo_db = configs["mongo_db"]
    mongo_port = configs["mongo_port"]
    # ----------------------------------------------------------------------
    # Build URI (SRV vs non-SRV)
    # ----------------------------------------------------------------------
    if is_srv:
        # configs["mongo_host"] like: mongodb+srv://cluster.mongodb.net
        host_part = configs["mongo_host"].replace("mongodb+srv://", "")
        uri = (
            f"mongodb+srv://{mongo_user}:{mongo_pwd}@{host_part}/"
            f"{mongo_db}"
        )
    else:
        uri = (
            f"mongodb://{mongo_user}:{mongo_pwd}"
            f"@localhost:{mongo_port}/{mongo_db}?"
            f"authSource={mongo_db}"
        )
    # ----------------------------------------------------------------------
    # Build mongoimport command (same structure for both modes)
    # ----------------------------------------------------------------------
    import_cmd = (
        f"mongoimport "
        f'--uri="{uri}" '
        f"--collection={destination} "
        f"--file={filepath}"
    )
    if drop:
        import_cmd += " --drop"
        logger.info("[mongoimport] Mode: drop existing documents")
    elif override:
        import_cmd += f" --mode=upsert --upsertFields={upsert_fields}"
        logger.info(f"[mongoimport] Mode: upsert override on fields={upsert_fields}")
    else:
        logger.info("[mongoimport] Mode: insert only")
    logger.info(f"[mongoimport] Executing on host via subprocess: {import_cmd}")
    try:
        subprocess.run(shlex.split(import_cmd), check=True)
        logger.info("[mongoimport] Import completed successfully (host mode)")
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
