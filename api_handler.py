import os
import sys
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException
from jinja2 import Environment, BaseLoader
from loguru import logger
from pydantic import BaseModel

from config_handler import get_lucidum_dir

AIRFLOW_DOCKER_FILENAME = "airflow_docker.py"

router = APIRouter(prefix="/update-manager/api")


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


def setup_logging():
    logger.remove()
    logger.add(sys.stdout, enqueue=True)
    logger.add("logs/api_{time}.log", rotation="1 day", retention="30 days", diagnose=True)

    logging.basicConfig(handlers=[InterceptHandler()], level=0)
    for log_ in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
        logger_ = logging.getLogger(log_)
        logger_.handlers = [InterceptHandler()]


class AirflowModel(BaseModel):
    template: str
    data: dict
    filename: Optional[str] = None


@router.post("/airflow", tags=["airflow"])
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


@router.get("/airflow", tags=["airflow"])
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


def create_app() -> FastAPI:
    app_ = FastAPI()
    app_.include_router(router)
    return app_


app = create_app()


@app.on_event("startup")
def startup_event():
    setup_logging()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0")
