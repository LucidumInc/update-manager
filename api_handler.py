import glob
import json
import subprocess
import uuid
from datetime import datetime, timezone

import base64
import os
import sys
import logging
import importlib
import requests
from typing import Optional, List

import shutil
import yaml
from openvpn_status import parse_status
from pymongo import MongoClient
from urllib.parse import quote_plus

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException, Request, Query
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
from install_handler import install_image_from_ecr, update_docker_compose_file, update_airflow_settings_file
import license_handler
from sqlalchemy import create_engine

from rsa import build_key_client
from service_status_handler import get_services_statuses

AIRFLOW_DOCKER_FILENAME = "airflow_docker.py"

root_router = APIRouter()
api_router = APIRouter(prefix="/update-manager/api")

templates = Jinja2Templates(directory="templates")

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


@api_router.get("/tunnel/client/keys")
def get_client_keyfile(
    name: str = Query(...),
    ip: Optional[str] = Query(None, regex=r"^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$")
):
    if ip is None:
        ip = get_public_ip_address()
    key_dir = f"{name}_{str(uuid.uuid4())}"
    try:
        ca_key_dir = get_key_dir_config()
        build_key_client(
            name, key_dir=key_dir,
            ca_key_filepath=os.path.join(ca_key_dir, "ca.key"),
            ca_crt_filepath=os.path.join(ca_key_dir, "ca.crt")
        )
        template = templates.get_template("client.conf.jinja2")
        template.stream(ip=ip, client_name=name).dump(os.path.join(key_dir, "client.conf"))
        filepath = f"{key_dir}.tar.gz"
        archive_directory(filepath, key_dir)
        return FileResponse(filepath, filename="conf.tar.gz", background=BackgroundTask(delete_file, filepath))
    finally:
        if os.path.isdir(key_dir):
            shutil.rmtree(key_dir)


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
    command = f'bash -c "python lucidum_{connector_type}.py test {technology} {profile_db_id}:{trace_id}"'
    out = run_docker_container(
        image, stdout=True, stderr=True, remove=True, network="lucidum_default", command=command
    )
    return {
        "status": "OK",
        "output": out.decode(),
    }


@api_router.post("/tunnel/clients")
def generate_client_configuration(tunnel_client: TunnelClientModel):
    client_name = tunnel_client.client_name
    container = get_docker_container("tunnel")
    create_client_cmd = f"easyrsa build-client-full {client_name} nopass"
    create_result = container.exec_run(create_client_cmd)
    if create_result.exit_code:
        error = create_result.output.decode()
        logger.error("Failed to create client configuration: {}?!", error)
        raise HTTPException(status_code=500, detail=error)
    export_client_config_cmd = f"ovpn_getclient {client_name}"
    export_result = container.exec_run(export_client_config_cmd)
    if export_result.exit_code:
        error = export_result.output.decode()
        logger.error("Failed to export client configuration: {}?!", error)
        raise HTTPException(status_code=500, detail=error)
    headers = {"Content-Disposition": f"attachment; filename={client_name}.conf"}
    return Response(content=export_result.output, headers=headers, media_type="text/plain")


@api_router.get("/tunnel/clients/{client_name}")
def get_client(client_name: str):
    container = get_docker_container("tunnel")
    status_cmd = "cat /tmp/openvpn-status.log"
    status_result = container.exec_run(status_cmd)
    if status_result.exit_code:
        error = status_result.output.decode()
        logger.error("Failed to get client status from openvpn-status.log: {}?!", error)
        raise HTTPException(status_code=500, detail=error)
    status = parse_status(status_result.output)
    client = None
    for address, client_ in status.client_list.items():
        if client_.common_name == client_name:
            client = {
                "common_name": client_.common_name,
                "real_address": address,
                "bytes_received": client_.bytes_received,
                "bytes_sent": client_.bytes_sent,
                "connected_since": client_.connected_since.isoformat(),
            }
            break

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client


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
