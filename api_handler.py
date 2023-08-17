import socket
import glob
import json
import subprocess
import uuid
from datetime import datetime, timezone, timedelta

import base64
import os
import sys
import logging
import importlib
import requests
from typing import Optional, List
from bson.json_util import dumps

import shutil
import yaml
from openvpn_status import parse_status
from pymongo import MongoClient
from urllib.parse import quote_plus

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException, Request, Query, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel, validator
from starlette.background import BackgroundTask

from config_handler import get_lucidum_dir, get_airflow_db_config, get_images, get_mongo_config, get_ecr_token, \
    get_key_dir_config, get_ecr_url, get_ecr_client, get_aws_config, get_ecr_base, get_source_mapping_file_path
from docker_service import start_docker_compose, stop_docker_compose, list_docker_compose_containers, \
    start_docker_compose_service, stop_docker_compose_service, restart_docker_compose, restart_docker_compose_service, \
    get_docker_compose_logs, run_docker_container, get_docker_container
from exceptions import AppError
from healthcheck_handler import get_health_information
from install_handler import install_image_from_ecr, update_docker_compose_file, update_airflow_settings_file, get_image_and_version
import license_handler
from sqlalchemy import create_engine

from rsa import build_key_client
from service_status_handler import get_services_statuses
import io
from dateutil import parser

AIRFLOW_DOCKER_FILENAME = "airflow_docker.py"

root_router = APIRouter()
api_router = APIRouter(prefix="/update-manager/api")

templates = Jinja2Templates(directory="templates")

import pydantic
from bson.objectid import ObjectId
pydantic.json.ENCODERS_BY_TYPE[ObjectId]=str

class MongoDBClient:
    _mongo_db = "test_database"
    _mongo_collection = "system_settings"

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            uri_pattern = "mongodb://{user}:{password}@{host}:{port}/?authSource={db}"

            configs = get_mongo_config()
            self._client = MongoClient(uri_pattern.format(
                user=quote_plus(configs["mongo_user"]),
                password=quote_plus(configs["mongo_pwd"]),
                host=configs["mongo_host"],
                port=configs["mongo_port"],
                db=configs["mongo_db"]
            ))
        return self._client

    def get_first_document(self):
        try:
            collection = self.client[self._mongo_db][self._mongo_collection]
            return collection.find_one({})
        except Exception as e:
            print(e)
            return {}


_db_client = MongoDBClient()


class InterceptHandler(logging.Handler):

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except AttributeError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, enqueue=True)
    logger.add("logs/api_{time}.log", rotation="1 day", retention="30 days", diagnose=True)

    logging.basicConfig(handlers=[InterceptHandler()], level=0)
    for log_ in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
        logger_ = logging.getLogger(log_)
        logger_.handlers = [InterceptHandler()]


def check_value_not_empty(v: str) -> Optional[str]:
    if v is not None and len(v) == 0:
        raise ValueError("must not be empty")
    return v


class EcrModel(BaseModel):
    image: str
    copy_default: bool
    restart_dockers: bool


class AirflowModel(BaseModel):
    template: str
    data: dict
    filename: Optional[str] = None


class PostAWSModel(BaseModel):
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None

    _validate_access_key = validator("aws_access_key", allow_reuse=True)(check_value_not_empty)
    _validate_secret_key = validator("aws_secret_key", allow_reuse=True)(check_value_not_empty)


class SSHTunnelsManagementModel(BaseModel):
    state: str
    customer_name: Optional[str] = None
    customer_number: Optional[int] = None


class InstallECRComponentModel(BaseModel):
    component_name: str
    component_version: str
    restart: bool = False
    copy_default: Optional[bool] = False
    update_files: Optional[bool] = False


class UpdateComponentVersionModel(BaseModel):
    component_name: str
    component_version: str
    files: List[str]

    @validator("files")
    def check_files_not_empty(cls, v):
        if not v:
            raise ValueError("should not be empty")
        return v

    @validator("files", each_item=True)
    def check_files_contains(cls, v):
        options = ["docker-compose", "airflow"]
        assert v in options, f"'{v}' should be one of {options}"
        return v


class TunnelClientModel(BaseModel):
    client_name: str


@api_router.get("/healthcheck", tags=["health"])
@api_router.get("/healthcheck/{category}", tags=["health"])
def get_health_status(category: str = None) -> dict:
    try:
        result = get_health_information(category)
    except AppError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return result


def write_settings(filename, data):
    loader_name = f"{filename.rpartition('.')[-1]}_loader"
    loader = importlib.import_module(f"dynaconf.loaders.{loader_name}")
    loader.write(filename, data, merge=True)


def update_ecr_token_config() -> None:
    # check if using access_id or secret_key to access ecr
    try:
        access_key, secret_key = get_aws_config()
        ecr_client = get_ecr_client(access_key, secret_key)
        auth_config = ecr_client.auth_config
        logger.info(auth_config)
        if auth_config['registry'] == get_ecr_base():
            logger.info('Not using ecr token for auth, no need to update ecr token')
            return
    except Exception as e:
        logger.warning(e)

    system_settings = _db_client.get_first_document()
    customer_name = system_settings["customer_name"]
    public_key = system_settings["public_key"]

    ecr_token = get_ecr_token()
    if ecr_token:
        ecr_token_decoded = base64.b64decode(ecr_token).decode()
        data = json.loads(base64.b64decode(ecr_token_decoded.rsplit(":", 1)[-1]).decode())
        current_timestamp = int(datetime.now(tz=timezone.utc).timestamp())
        if current_timestamp <= data["expiration"]:
            return
    ecr_url = get_ecr_url()
    token = requests.get(f"{ecr_url}/{customer_name}", verify=False)
    _, public_key = license_handler.reformat_keys(pub_key=public_key)
    token_dict = {"global": {"ecr_token": license_handler.decrypt(token.json()["ecr_token"], public_key)}}
    write_settings("settings.toml", token_dict)


@api_router.post("/ecr")
def update_ecr_token(param: EcrModel):
    update_ecr_token_config()

    return {
        "status": "OK",
        "message": "success",
    }


@api_router.post("/installecr", tags=["installecr"])
def installecr(component: InstallECRComponentModel):
    components = [f"{component.component_name}:{component.component_version}"]
    logger.info(
        "ecr components: {}, copy default: {}, restart: {}, update files: {}",
        components, component.copy_default, component.restart, component.update_files
    )
    update_ecr_token_config()
    images = get_images(components)
    logger.info(json.dumps(images, indent=2))
    install_image_from_ecr(images, component.copy_default, component.restart, update_files=component.update_files)

    return {
        "status": "OK",
        "message": "success",
    }


@api_router.post("/update/version", tags=["update-version"])
def update_files(component: UpdateComponentVersionModel):
    components = [{"name": component.component_name, "version": component.component_version}]
    if "docker-compose" in component.files:
        update_docker_compose_file(components)
    if "airflow" in component.files:
        update_airflow_settings_file(components)

    return {
        "status": "OK",
        "message": "success",
    }


def handle_start_action(component_name: str = None):
    lucidum_dir = get_lucidum_dir()
    if component_name is not None:
        services = list_docker_compose_containers(lucidum_dir, services=True)
        running_services = list_docker_compose_containers(lucidum_dir, services=True, filter_="status=running")
        if component_name not in services.split():
            raise HTTPException(status_code=404, detail=f"Component not found: {component_name}")
        if component_name not in running_services.split():
            start_docker_compose_service(lucidum_dir, component_name)
    else:
        start_docker_compose(lucidum_dir)
    return list_docker_compose_containers(lucidum_dir)


def handle_stop_action(component_name: str = None):
    lucidum_dir = get_lucidum_dir()
    if component_name is not None:
        services = list_docker_compose_containers(lucidum_dir, services=True)
        running_services = list_docker_compose_containers(lucidum_dir, services=True, filter_="status=running")
        if component_name not in services.split():
            raise HTTPException(status_code=404, detail=f"Component not found: {component_name}")
        if component_name in running_services.split():
            stop_docker_compose_service(lucidum_dir, component_name)
    else:
        stop_docker_compose(lucidum_dir)
    return list_docker_compose_containers(lucidum_dir)


def handle_restart_action(component_name: str = None):
    lucidum_dir = get_lucidum_dir()
    if component_name is not None:
        services = list_docker_compose_containers(lucidum_dir, services=True)
        if component_name not in services.split():
            raise HTTPException(status_code=404, detail=f"Component not found: {component_name}")
        restart_docker_compose_service(lucidum_dir, component_name)
    else:
        restart_docker_compose(lucidum_dir)
    return list_docker_compose_containers(lucidum_dir)


def handle_logs_action(component_name: str = None, tail: int = 2000):
    if not 0 <= tail <= 10000:
        raise HTTPException(status_code=400, detail="Parameter 'tail' should be in range 0-10000")
    lucidum_dir = get_lucidum_dir()
    list_result = list_docker_compose_containers(lucidum_dir, services=True)
    services = list_result.split()
    if component_name is not None:
        if component_name not in services:
            raise HTTPException(status_code=404, detail=f"Component not found: {component_name}")
        output = get_docker_compose_logs(lucidum_dir, component_name, tail)
    else:
        tail_per_service = int(tail / len(services))
        output = get_docker_compose_logs(lucidum_dir, tail=tail_per_service)
    return output


@api_router.get("/docker-compose", tags=["docker-compose"])
@api_router.get("/docker-compose/{component_name}", tags=["docker-compose"])
def manage_docker_compose_actions(component_name: str = None, action: str = None, lines: int = 2000):
    if action == "start":
        output = handle_start_action(component_name)
    elif action == "stop":
        output = handle_stop_action(component_name)
    elif action == "restart":
        output = handle_restart_action(component_name)
    elif action == "logs":
        output = handle_logs_action(component_name, lines)
    else:
        raise HTTPException(status_code=400, detail=f"Wrong action: {action}")

    return {
        "status": "OK",
        "message": "success",
        "output": output,
    }


def get_public_ip_address() -> str:
    return requests.get("https://api.ipify.org").text


def delete_file(filepath: str) -> None:
    if os.path.isfile(filepath):
        os.remove(filepath)


def archive_directory(filepath: str, dir_name: str) -> None:
    cmd = f"tar -czvf {filepath} --directory={dir_name} ."
    try:
        subprocess.run(cmd.split(), check=True)
    except Exception:
        delete_file(filepath)
        raise

@api_router.get("/connector/mapping")
def get_connector_mapping():
    result = []
    source_mapping_file_path = get_source_mapping_file_path()
    for path in glob.glob(source_mapping_file_path):
        with open(path) as f:
            for item in json.load(f):
                result.append({"connector_name": item['platform'], "type": item['type'], "service": item['technology']})
    result = [i for n, i in enumerate(result) if i not in result[n + 1:]]
    return result


@api_router.get("/services/status")
def get_services_statuses_():
    statuses = get_services_statuses()
    return {
        "data": statuses,
    }

def get_connector_version(connector_type: str) -> Optional[str]:
    lucidum_dir = get_lucidum_dir()
    airflow_settings_file_path = os.path.join(lucidum_dir, "airflow", "dags", "settings.yml")
    if not os.path.isfile(airflow_settings_file_path):
        logger.warning("'{}' file does not exist", airflow_settings_file_path)
        return
    with open(airflow_settings_file_path) as f:
        data = yaml.full_load(f)
    connector_version = None
    if "global" in data and "connectors" in data["global"]:
        connectors = data["global"]["connectors"]
        if connector_type not in connectors:
            logger.warning("Connector not found within airflow settings: {}", connector_type)
            return
        if "version" not in connectors[connector_type]:
            logger.warning("Connector version not found within airflow settings: {}", connector_type)
            return
        connector_version = connectors[connector_type]["version"]
    else:
        logger.warning("'global' or 'connectors' keys are not found within airflow settings")

    return connector_version


@api_router.get("/connector/{connector_type}/test/{technology}")
def run_connector_test_command(connector_type: str, technology: str, profile_db_id: str, trace_id: str):
    """Run connector test command.
        :param connector_type (str): api, gcp, aws, azure
        :param technology (str): ad_ldap, okta
        :param profile_db_id (str): ui connector config db id
        :param trace_id (str): trace_id for this API, unique for each API
        """
    connector_version = get_connector_version(connector_type)
    if not connector_version:
        return JSONResponse(content={"status": "FAILED", "output": "can't find image version"}, status_code=404)
    image = f"connector-{connector_type}:{connector_version}"
    # api and sdk connections has technology
    command = f'bash -c "python lucidum_{connector_type}.py test {technology} {profile_db_id}:{trace_id}"'    
    if connector_type not in ['api', 'sdk']: # cloud connectors default test all services
        command = f'bash -c "python lucidum_{connector_type}.py test {profile_db_id}:{trace_id}"'
    # only connector-sdk need docker privilege to access host network
    docker_privileged = False
    if connector_type in ['sdk']:
        docker_privileged = True
    out = run_docker_container(
        image, stdout=True, stderr=True, remove=True, network="lucidum_default", privileged=docker_privileged, command=command
    )
    return {
        "status": "OK",
        "output": out.decode(),
    }

def get_local_connectors():
    result = []
    lucidum_dir = get_lucidum_dir()
    airflow_settings_file_path = os.path.join(lucidum_dir, "airflow", "dags", "settings.yml")
    if not os.path.isfile(airflow_settings_file_path):
        logger.warning("'{}' file does not exist", airflow_settings_file_path)
        return result
    with open(airflow_settings_file_path) as f:
        data = yaml.full_load(f)
        if "global" in data and "connectors" in data["global"]:
            connectors = data["global"]["connectors"]
            for connector in connectors:
                result.append({"type": connector, "version": connectors[connector]['version']})
    return result

@api_router.get("/connector/config-to-db")
def run_connector_config_to_db():
    connectors = get_local_connectors()
    result = []
    for connector in connectors:
        image = f"connector-{connector['type']}:{connector['version']}"
        command = f'bash -c "python lucidum_{connector["type"]}.py config-to-db"'
        out = run_docker_container(
            image, stdout=True, stderr=True, remove=True, network="lucidum_default", command=command
        )
        result.append({
            "status": "OK",
            "output": out.decode(),
        })
    return result

@api_router.get("/images")
def get_docker_image_and_version():
    return get_image_and_version()

@api_router.post("/tunnel/clients")
def generate_client_configuration(tunnel_client: TunnelClientModel):
    client_name = tunnel_client.client_name
    client_name_list = get_tunnel_client_dict().keys()
    container = get_docker_container("tunnel")
    # create tunnel client with client_name
    if client_name not in client_name_list:
        create_client_cmd = f"easyrsa build-client-full {client_name} nopass"
        create_result = container.exec_run(create_client_cmd)
        if create_result.exit_code:
            error = create_result.output.decode()
            logger.error("Failed to create client configuration: {}?!", error)
            raise HTTPException(status_code=500, detail=error)
    # export tunnel client config file
    export_client_config_cmd = f"ovpn_getclient {client_name}"
    export_result = container.exec_run(export_client_config_cmd)
    if export_result.exit_code:
        error = export_result.output.decode()
        logger.error("Failed to export client configuration: {}?!", error)
        raise HTTPException(status_code=500, detail=error)
    headers = {"Content-Disposition": f"attachment; filename={client_name}.conf"}
    return Response(content=export_result.output, headers=headers, media_type="text/plain")

def get_tunnel_client_dict():
    container = get_docker_container("tunnel")
    client_list_cmd = "ovpn_listclients"
    client_list_result = container.exec_run(client_list_cmd)
    client_list_result.output
    string = client_list_result.output.decode('utf-8')
    buf = io.StringIO(string)
    result = buf.readlines()
    clients = {}
    for record in result:
        if record.split(',')[0] != 'name':
            items = record.split(',')
            clients[items[0]] = parser.parse(items[2]).isoformat()
    return clients

@api_router.get("/tunnel/clients")
def get_clients():
    container = get_docker_container("tunnel")
    status_cmd = "cat /tmp/openvpn-status.log"
    status_result = container.exec_run(status_cmd)
    if status_result.exit_code:
        error = status_result.output.decode()
        logger.error("Failed to get clients from openvpn-status.log: {}?!", error)
        raise HTTPException(status_code=500, detail=error)
    status = parse_status(status_result.output)
    routing_table = {client_.common_name: client_ for client_ in status.routing_table.values()}
    tunnel_client_dict = get_tunnel_client_dict()
    clients = []
    for client_ in status.client_list.values():
        client = {
            "name": client_.common_name,
            "real_address": str(client_.real_address),
            "bytes_received": client_.bytes_received,
            "bytes_sent": client_.bytes_sent,
            "connected_since": client_.connected_since.isoformat(),
            "status": "connected"
        }
        if client_.common_name in routing_table:
            client["proxy_address"] = str(routing_table[client_.common_name].virtual_address)
        if client['name'] in tunnel_client_dict:
            client['config_expire_date'] = tunnel_client_dict[client['name']]
        clients.append(client)
    for name, expire_date in tunnel_client_dict.items():
        if name not in routing_table:
            clients.append({'name': name, 'status': 'disconnected', 'config_expire_date': expire_date})

    return {"clients": clients,}


def filter_connector_metrics(from_: str = Query(None, alias='from'), to_: str = Query(None, alias='to')):
    if not from_:
        raise AppError('Query parameter "from_" is required')
    try:
        datetime_from = datetime.strptime(from_, '%Y-%m-%d')
        filters = {'_utc': {"$gte": datetime_from}}
        if to_:
            datetime_to = datetime.strptime(to_, '%Y-%m-%d')
            if datetime_from > datetime_to:
                raise AppError('query parameter "from" should be less or equal to query parameter "to"')
            filters['_utc'].update({'$lte': datetime_to})
    except ValueError:
        raise ValueError("Incorrect data format, should be YYYY-MM-DD")
    return filters


@api_router.get("/connector/metrics", tags=['metrics'])
def get_connector_metric(filters: dict = Depends(filter_connector_metrics)):
    db_client = MongoDBClient()
    collections = db_client.client[db_client._mongo_db]['metrics'].find(filters)
    return {"data": list(collections)}

def get_fqdn():
    return f"{socket.gethostname()}.lucidum.cloud"

@api_router.get("/connector/list")
def get_connector_list_from_db():
    result = []
    db_client = MongoDBClient()
    collection_name = 'local_connector_configuration'
    collection = db_client.client[db_client._mongo_db][collection_name]
    for item in collection.find({'active': True}):
        for service in item.get('services_list', []):
            # status == OK is test passed, activity == True is selected
            if service.get('status', None) == 'OK' and service.get('activity', None) == True:
                result.append({'service': service['service'],
                               'service_display_name': service.get('display_name', service['service']),
                               'connector': item['connector_name'],
                               'profile_db_id': str(item['_id']),
                               'bridge_name': item['bridge_name'],
                               'bridge_display_name': item.get('display_name', item['bridge_name'])
                              })
    return result

def parse_web_log(date_str, user_email_dict):
    cmd = f'sudo cat /usr/lucidum/web/app/logs/logFile.{date_str}.log'
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    result = []
    for line_bytes in iter(process.stdout.readline, ''):
        line = line_bytes.decode()
        if not line:
            break
        if "User successfully logged in" in line:
            items = line.strip().split(' ')
            if len(items) > 12:
                username = items[12][:-1]
                result.append({
                    "datetime": f"{items[0]}T{items[1]}Z",
                    "type": "SSO",
                    "username": username,
                    "email": user_email_dict.get(username)
                })
            else:
                result.append({
                    "datetime": f"{items[0]}T{items[1]}Z",
                    "type": "LOGIN",
                    "username": items[-1],
                    "email": user_email_dict.get(items[-1])
                })
    return result

@api_router.get("/ui/login/metrics")
def get_ui_login_metrics():
    # returns user login logs for passed 7 days
    user_email_dict = {} # username to email mapping from db
    db_client = MongoDBClient()
    records = db_client.client[db_client._mongo_db]['jhi_user'].find({})
    for item in records:
        user_email_dict[item['login']] = item['email']
    base = datetime.today()
    date_list = [base - timedelta(days=x) for x in range(7)]
    result = []
    for d in date_list:
        result += parse_web_log(d.strftime("%Y-%m-%d"), user_email_dict)
    return result

@api_router.get("/data/values", tags=['dataValues'])
def get_data_values(collection, field):
    db_client = MongoDBClient()
    records = db_client.client[db_client._mongo_db][collection].aggregate([{'$sortByCount': f'${field}'}])
    fqdn = get_fqdn()
    result = {"customer_name": fqdn.replace(".lucidum.cloud", ""), "values": {}}
    for record in records:
        if record['_id']:
            # record['_id'] could be list or string
            if isinstance(record['_id'], list):
                for value in record['_id']:
                    if value:
                        result["values"][value] = result["values"].get(value, 0) + record['count']
            else:
                result["values"][record['_id']] = result["values"].get(record['_id'], 0) + record['count']
    return result

@api_router.get("/host/network")
def get_host_network():
    result = {}
    result['host_ip'] = socket.gethostbyname(socket.gethostname() + ".local")
    result['host_fqdn'] = f"{socket.gethostname()}.lucidum.cloud"
    return result

@root_router.get("/setup", response_class=HTMLResponse, tags=["setup"])
def get_setup(request: Request):
    return templates.TemplateResponse("index.html.jinja2", {"request": request})


def startup_event() -> None:
    setup_logging()


def setup_startup_event(app_: FastAPI) -> None:
    app_.add_event_handler("startup", startup_event)


def default_exception_handler(request, exc) -> JSONResponse:
    return JSONResponse(content={"status": "FAILED", "message": repr(exc)}, status_code=500)


def http_exception_handler(request, exc) -> JSONResponse:
    return JSONResponse(content={"status": "FAILED", "message": str(exc.detail)}, status_code=exc.status_code)


def setup_exception_handlers(app_: FastAPI) -> None:
    app_.add_exception_handler(Exception, default_exception_handler)
    app_.add_exception_handler(HTTPException, http_exception_handler)


def create_app() -> FastAPI:
    app_ = FastAPI()

    app_.mount("/static", StaticFiles(directory="static", html=True), name="static")
    app_.include_router(root_router)
    app_.include_router(api_router)

    setup_startup_event(app_)
    setup_exception_handlers(app_)
    return app_


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
