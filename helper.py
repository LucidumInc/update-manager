import uuid
import json
import requests
from api_handler import MongoDBClient
from loguru import logger
from bson.objectid import ObjectId
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

db_client = MongoDBClient()
connector_table_name = 'local_connector_configuration'
connector_table = db_client.client[db_client._mongo_db][connector_table_name]
connector_test_result_table = db_client.client[db_client._mongo_db]['connector_test_result']
action_config_table = db_client.client[db_client._mongo_db]['local_integration_configuration']


def get_all_connector_profiles():
    result = []
    for item in connector_table.find():
        for service in item.get('services_list', []):
            result.append({'service': service['service'],
                           'service_display_name': service.get('display_name', service['service']),
                           'service_enabled': service.get('activity', False),
                           'service_status': service.get('status'),
                           'connector_name': item['connector_name'],
                           'profile_id': str(item['_id']),
                           'profile_name': item['profile_name'],
                           'profile_enabled': item.get('active', False),
                           'bridge_name': item['bridge_name'],
                           'bridge_display_name': item.get('display_name', item['bridge_name'])
                           })
    return result


def get_active_connector_profiles():
    results = []
    for item in connector_table.find({'active': True}):
        for service in item.get('services_list', []):
            if service.get('activity', None) is True:
                results.append({'bridge_name': item['bridge_name'],
                                'connector_name': item['connector_name'],
                                'profile_name': item['profile_name'],
                                'profile_id': str(item["_id"])
                                })
    if results and len(results) > 0:
        results = [i for n, i in enumerate(results) if i not in results[n + 1:]]
        logger.info(f'got {len(results)} results from database {connector_table_name}')
    return results


def run_connector_profile_test():
    logger.info(">>> testing connector profiles start...")
    records = get_active_connector_profiles()
    collection = connector_test_result_table

    def test_profile(record):
        try:
            logger.info(f"test connector: {record}")
            trace_id = uuid.uuid4().hex
            url = (
                f"http://localhost:8000/update-manager/api/connector/"
                f"{record['connector_name']}/test/{record['bridge_name']}"
                f"?profile_db_id={record['profile_id']}&trace_id={trace_id}"
            )
            requests.get(url)
            test_results = collection.find_one({'trace_id': trace_id})
            if not test_results:
                logger.info(f'no test result for trace_id {trace_id}')
                return
            logger.info(f"test connector result: {test_results}")
            connector_config = connector_table.find_one({'_id': ObjectId(test_results['profile_db_id'])})
            can_update = False
            for test_result in test_results['test_result']:
                for service in connector_config['services_list']:
                    if test_result['name'] == service['service']:
                        service['status'] = test_result['status']
                        service['message'] = test_result['message']
                        can_update = True
            if can_update:
                connector_table.update_one(
                    {"_id": ObjectId(test_results['profile_db_id'])},
                    {"$set": {
                        "services_list": connector_config['services_list'],
                        "last_tested_at": datetime.now()
                    }}
                )
                logger.info(f"DB test result updated for profile {test_results['profile_db_id']}")
        except Exception as e:
            logger.warning(f"Error testing connector profile {record}: {e}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(test_profile, records)

    logger.info(">>> testing connector profiles Done.")


def get_all_action_configs():
    results = []
    collection = action_config_table
    for item in collection.find({}):
        results.append({"bridge_name": item['bridge_name'], "config_name": item["config_name"], "_id": item["_id"]})
    return results


def run_action_config_test():
    logger.info(">>> testing action config start...")
    collection = action_config_table
    results = get_all_action_configs()

    def test_action_config(result):
        url = (f"http://localhost:8000/update-manager/api/action-manager/connection/"
               f"{result['bridge_name']}/{result['config_name']}")
        try:
            logger.info(f"test action config: {result}")
            resp = requests.get(url)
            logger.info(f"test action config result: {resp.text}")
            # collection.update_one({"_id": result["_id"]},
            #                       {"$set": {"test_status": resp.json(), "last_tested_at": datetime.now()}})
        except Exception as e:
            logger.warning(f"{url} error {e}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(test_action_config, results)

    logger.info(">>> testing action config Done.")


if __name__ == "__main__":
    # run_connector_profile_test()
    run_action_config_test()
