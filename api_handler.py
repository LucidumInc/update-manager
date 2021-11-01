import json
from datetime import datetime, timezone

import base64
import os
import sys
import logging
import importlib
import requests
from typing import Optional, List
from pymongo import MongoClient
from urllib.parse import quote_plus
from dynaconf import loaders

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, BaseLoader
from loguru import logger
from pydantic import BaseModel, validator

from config_handler import get_lucidum_dir, get_airflow_db_config, get_images, get_mongo_config, get_ecr_token
from docker_service import start_docker_compose, stop_docker_compose
from exceptions import AppError
from healthcheck_handler import get_health_information
from install_handler import install_image_from_ecr
from ssh_tunnels_handler import enable_jumpbox_tunnels, disable_jumpbox_tunnels
import license_handler
from sqlalchemy import create_engine

AIRFLOW_DOCKER_FILENAME = "airflow_docker.py"

root_router = APIRouter()
api_router = APIRouter(prefix="/update-manager/api")

templates = Jinja2Templates(directory="templates")
airflow_db = get_airflow_db_config()
airflow_db_connection = create_engine(f"postgresql://{airflow_db['user']}:{airflow_db['pwd']}@{airflow_db['host']}:{airflow_db['port']}/{airflow_db['db']}").connect()


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
def get_airflow_dag_runs(dag_id: str = None, execution_date: str = None) -> dict:
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

    token = requests.get(f"http://127.0.0.1:5500/ecr/token/{customer_name}")
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


@api_router.post("/docker-compose/start", tags=["docker-compose"])
def start_docker_compose_():
    lucidum_dir = get_lucidum_dir()
    start_docker_compose(lucidum_dir)
    return {
        "status": "OK",
        "message": "success",
    }


@api_router.post("/docker-compose/stop", tags=["docker-compose"])
def stop_docker_compose_():
    lucidum_dir = get_lucidum_dir()
    stop_docker_compose(lucidum_dir)
    return {
        "status": "OK",
        "message": "success",
    }


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
