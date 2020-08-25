import json
import os
import sys
from urllib.parse import quote_plus

from loguru import logger
from pymongo import MongoClient

from config_handler import get_local_images, get_mongo_config, is_connector


class MongoDBClient:
    MONGO_URI_FORMAT = "mongodb://{user}:{password}@{host}:{port}/?authSource={db}"

    def __init__(self, mongo_host, mongo_user, mongo_pwd, mongo_port, mongo_db) -> None:
        self._uri = self.MONGO_URI_FORMAT.format(
            user=quote_plus(mongo_user), password=quote_plus(mongo_pwd), host=mongo_host, port=mongo_port, db=mongo_db
        )
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = MongoClient(self._uri)
        return self._client

    def insert(self, collection, data):
        return collection.insert_one(data)

    def drop(self, collection):
        return collection.drop()


mongo_client = MongoDBClient(**get_mongo_config())


def _get_output_manager(output: str):
    if output == "mongo":
        return mongo_client


def _get_connector_aws_bridges(path):
    source_config_file = next(
        f for f in [os.path.join(path, "source-mapping.json"), os.path.join(path, "source-mapping.json.example")]
        if os.path.exists(f)
    )
    with open(source_config_file) as f:
        configs = json.load(f)

    bridges = []
    for config in configs:
        bridges.append({
            "name": config["technology"],
            "dataCategory": config["type"],
            "services": config["services"]
        })

    return {
        "connection": {
            "name": "aws",
            "technology": "aws",
            "type": "",
            "bridges": bridges
        }
    }


@logger.catch(onerror=lambda _: sys.exit(1))
def run(output):
    images = get_local_images()
    if not any(is_connector(image["name"]) for image in images):
        logger.warning("No connectors found")
        return
    logger.info("Writing connectors bridge information to '{}' source...", output)
    output_manager = _get_output_manager(output)
    collection = "localConnector"
    output_manager.drop(output_manager.client.test_database[collection])
    for image in images:
        host_path = image.get("hostPath")
        if image["name"] == "connector-aws" and host_path and os.path.exists(host_path):
            data = _get_connector_aws_bridges(host_path)
            logger.info("{} bridge information:\n{}", image["name"], json.dumps(data, indent=2))
            result = output_manager.insert(output_manager.client.test_database[collection], data)
            logger.info(
                "{} bridge information was written to {} collection: {}", image["name"], collection, result.inserted_id
            )
