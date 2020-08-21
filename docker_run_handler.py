import sys

from loguru import logger

from config_handler import docker_client, get_local_images
from exceptions import AppError

NETWORK = "lucidum_default"


def run_command(image_data: dict, cmd: str):
    image_name = f"{image_data['name']}:{image_data['version']}"
    kwargs, message = {}, [f"Docker image: {image_name}"]
    host_path, docker_path = image_data.get("hostPath"), image_data.get("dockerPath")
    if host_path and docker_path:
        message += [f"Host path: {host_path}", f"Docker path: {docker_path}"]
        kwargs["volumes"] = {
            host_path: {
                "bind": docker_path,
                "mode": "rw"
            }
        }
    message.append(f"Network: {NETWORK}")
    logger.info("Docker run parameters:\n{}", "\n".join(message))
    docker_client.containers.run(image_name, remove=True, network=NETWORK, command=cmd, **kwargs)


@logger.catch(onerror=lambda _: sys.exit(1))
def run(component: str, cmd: str):
    image_data = next(
        (image for image in get_local_images() if f"{image['name']}:{image['version']}" == component), None
    )
    if not image_data:
        raise AppError(f"Component '{component}' was not found in image list")
    logger.info("Running command within '{}' component: {}", component, cmd)
    run_command(image_data, cmd)
