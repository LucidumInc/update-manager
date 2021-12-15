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
from typing import Optional

import shutil
from pymongo import MongoClient
from urllib.parse import quote_plus

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel, validator
from starlette.background import BackgroundTask

from config_handler import get_lucidum_dir, get_airflow_db_config, get_images, get_mongo_config, get_ecr_token, \
    get_key_dir_config, get_ecr_url, get_ecr_client, get_aws_config, get_ecr_base
from docker_service import start_docker_compose, stop_docker_compose, list_docker_compose_containers, \
    start_docker_compose_service, stop_docker_compose_service, restart_docker_compose, restart_docker_compose_service, \
    get_docker_compose_logs
from exceptions import AppError
from healthcheck_handler import get_health_information
from install_handler import install_image_from_ecr
import license_handler
from sqlalchemy import create_engine

from rsa import build_key_client

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


@api_router.get("/airflow", tags=["airflow"])
def get_airflow_dag_file() -> dict:
    try:
        with open(os.path.join(get_lucidum_dir(), "airflow", "dags", AIRFLOW_DOCKER_FILENAME)) as f:
            content = f.read()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Airflow file was not found") from e

    return {
        "status": "OK",
        "message": "success",
        "file_content": content,
    }

@api_router.get("/airflow/dags/{dag_id}/dagRuns", tags=["airflow"])
def get_airflow_dag_runs(dag_id: str = None) -> dict:
    query = f"""select dag_id, run_id, execution_date, end_date - start_date AS duration
                  from dag_run
                 where dag_id = '{dag_id}'
                 order by start_date desc
                 limit 10"""
    records = airflow_db_connection.execute(query).fetchall()
    results = [dict(row) for row in records]
    return {
        "status": "OK",
        "message": "success",
        "data": results
    }

@api_router.get("/airflow/dags/{dag_id}/dagRuns/{execution_date}/tasks", tags=["airflow"])
def get_airflow_dag_runs_tasks(dag_id: str = None, execution_date: str = None) -> dict:
    query = f"""select task_id, dag_id, execution_date, start_date, end_date, duration, state, try_number, job_id, pid
                  from task_instance
                 where dag_id = '{dag_id}'
                   and execution_date = '{execution_date}'
                 order by job_id"""
    records = airflow_db_connection.execute(query).fetchall()
    results = [dict(row) for row in records]
    return {
        "status": "OK",
        "message": "success",
        "data": results
    }


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
    customer_name = system_settings["company_name"]
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
    logger.info(f"ecr components: {components}, copy default: {component.copy_default}, restart: {component.restart}")
    update_ecr_token_config()
    images = get_images(components)
    logger.info(json.dumps(images, indent=2))
    install_image_from_ecr(images, component.copy_default, component.restart)

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
    if not (0 <= tail <= 10000):
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


@api_router.get("/tunnel/client/keys")
def get_client_keyfile(
    name: str = Query(...),
    ip: Optional[str] = Query(None, regex="^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$")
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
    uvicorn.run(app, host="0.0.0.0")
