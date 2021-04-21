import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException
from jinja2 import Environment, BaseLoader
from pydantic import BaseModel

from config_handler import get_lucidum_dir

AIRFLOW_DOCKER_FILENAME = "airflow_docker.py"

router = APIRouter(prefix="/update-manager/api")


class AirflowModel(BaseModel):
    template: str
    data: dict
    filename: Optional[str] = None


@router.post("/airflow", tags=["airflow"])
def generate_airflow_dag_file(airflow: AirflowModel):
    template = Environment(loader=BaseLoader(), extensions=["jinja2.ext.do"]).from_string(airflow.template)
    content = template.render(**airflow.data)
    try:
        compile(content, "airflow", "exec")
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=str(e))
    filename = airflow.filename or AIRFLOW_DOCKER_FILENAME
    with open(os.path.join(get_lucidum_dir(), "airflow", "dags", filename), "w+") as f:
        f.write(content)

    return {
        "status": "OK",
        "message": "success",
        "file_content": content,
    }


def create_app():
    app_ = FastAPI()
    app_.include_router(router)
    return app_


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0")
