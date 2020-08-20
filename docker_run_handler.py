import sys

from loguru import logger

from config_handler import get_ecr_images, docker_client
from exceptions import AppError

NETWORK = "lucidum_default"


def run_command(image_data: dict, cmd: str):
    kwargs = {}
    if cmd:
        kwargs["command"] = cmd
    host_path, docker_path = image_data.get("hostPath"), image_data.get("dockerPath")
    if host_path and docker_path:
        kwargs["volumes"] = {
            host_path: {
                "bind": docker_path,
                "mode": "rw"
            }
        }
    docker_client.containers.run(
        f"{image_data['name']}:{image_data['version']}", remove=True, network=NETWORK, **kwargs
    )


@logger.catch(onerror=lambda _: sys.exit(1))
def run(component: str, cmd: str):
    image_data = next((image for image in get_ecr_images() if f"{image['name']}:{image['version']}" == component), None)
    if not image_data:
        raise AppError(f"Component '{component}' was not found in image list")
    run_command(image_data, cmd)
