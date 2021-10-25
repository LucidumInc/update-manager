import json

import os
import sys
import logging
import importlib
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, BaseLoader
from loguru import logger
from pydantic import BaseModel, validator

from config_handler import get_lucidum_dir, get_images
from exceptions import AppError
from healthcheck_handler import get_health_information
from install_handler import install_image_from_ecr
from ssh_tunnels_handler import enable_jumpbox_tunnels, disable_jumpbox_tunnels

AIRFLOW_DOCKER_FILENAME = "airflow_docker.py"

root_router = APIRouter()
api_router = APIRouter(prefix="/update-manager/api")

templates = Jinja2Templates(directory="templates")


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


class InstallECRModel(BaseModel):
    components: List[dict]
    restart: bool
    copy_default: Optional[bool] = False


@api_router.post("/airflow", tags=["airflow"])
def generate_airflow_dag_file(airflow: AirflowModel) -> dict:
    template = Environment(loader=BaseLoader(), extensions=["jinja2.ext.do"]).from_string(airflow.template)
    content = template.render(**airflow.data)
    try:
        compile(content, "airflow", "exec")
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    filename = airflow.filename or AIRFLOW_DOCKER_FILENAME
    airflow_dags_path = os.path.join(get_lucidum_dir(), "airflow", "dags")
    os.makedirs(airflow_dags_path, exist_ok=True)
    with open(os.path.join(airflow_dags_path, filename), "w+") as f:
        f.write(content)

    return {
        "status": "OK",
        "message": "success",
        "file_content": content,
    }


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


@api_router.post("/aws", tags=["aws"])
def update_aws_settings(config: PostAWSModel) -> dict:
    global_config = {
        "aws_access_key": config.aws_access_key,
        "aws_secret_key": config.aws_secret_key,
    }
    write_settings("settings.toml", {"global": global_config})

    return {
        "status": "OK",
        "message": "success",
    }


@api_router.post("/ssh-tunnels", tags=["ssh_tunnels"])
def manage_ssh_tunnels(config: SSHTunnelsManagementModel):
    if config.state == "enable":
        if not config.customer_name:
            raise HTTPException(status_code=400, detail="Field 'customer_name' is required")
        if not config.customer_number:
            raise HTTPException(status_code=400, detail="Field 'customer_number' is required")
        jumpbox_primary_content, jumpbox_secondary_content = enable_jumpbox_tunnels(
            config.customer_name, config.customer_number
        )
        logger.debug("lucidum-jumpbox-primary service:\n{}", jumpbox_primary_content)
        logger.debug("lucidum-jumpbox-secondary service:\n{}", jumpbox_secondary_content)
    else:
        disable_jumpbox_tunnels()

    return {
        "status": "OK",
        "message": "success",
    }


@api_router.post("/installecr", tags=["installecr"])
def installecr(data: InstallECRModel):
    components = [f"{component['component']}:{component['version']}" for component in data.components]
    logger.info(f"ecr components: {components}, copy default: {data.copy_default}, restart: {data.restart}")
    images = get_images(components)
    logger.info(json.dumps(images, indent=2))
    install_image_from_ecr(images, data.copy_default, data.restart)

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
