import time

import os
import re
import shutil
import tarfile
from docker.models.images import Image
from io import BytesIO
from loguru import logger

from config_handler import get_ecr_client, docker_client

ECR_REGISTRY_PATTERN = r"\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/.+"


def _pull_docker_image_from_ecr(repository: str, tag: str = None):
    ecr_client = get_ecr_client()
    auth_config = {"username": ecr_client.auth_config["username"], "password": ecr_client.auth_config["password"]}
    docker_client.images.pull(repository, tag=tag, auth_config=auth_config)


def _pull_docker_image_from_docker_hub(repository: str, tag: str = None):
    docker_client.images.pull(repository, tag=tag)


def pull_docker_image(repository: str, tag: str = None) -> Image:
    docker_image_puller = _pull_docker_image_from_docker_hub
    if re.match(ECR_REGISTRY_PATTERN, repository):
        docker_image_puller = _pull_docker_image_from_ecr
    image_tag = repository
    if tag:
        image_tag = f"{image_tag}:{tag}"
    logger.info("Pulling '{}' image...", image_tag)
    docker_image_puller(repository, tag)
    return docker_client.images.get(image_tag)


def load_docker_images(filepath: str) -> list:
    """Load docker images from given file path."""
    with open(filepath, "rb") as f:
        return docker_client.images.load(f)


def remove_docker_image(image: str) -> None:
    logger.info("Removing '{}' image...", image)
    docker_client.images.remove(image, force=True)


def copy_files_from_docker_container(image: Image, docker_path, host_path):
    if not os.path.exists(host_path):
        os.makedirs(host_path)
    else:
        logger.warning(f"host_path: {host_path} already exists, won't overwrite.")
        return
    logger.info("Copy files from {} docker {} to host {}", image.tags, docker_path, host_path)
    container = docker_client.containers.create(image, 'bash')
    filename = os.path.join(host_path, "docker.tar")
    try:
        bits, _ = container.get_archive(f"{docker_path}/.")
        with open(filename, 'wb') as f:
            for chunk in bits:
                f.write(chunk)
        shutil.unpack_archive(filename, extract_dir=host_path)
    finally:
        logger.info("clean up")
        container.remove()
        if os.path.isfile(filename):
            os.remove(filename)


def create_archive(filepath: str):
    tar_stream = BytesIO()
    tar = tarfile.TarFile(fileobj=tar_stream, mode='w')
    with open(filepath, "rb") as f:
        file_data = f.read()
    tarinfo = tarfile.TarInfo(name=os.path.basename(filepath))
    tarinfo.size = len(file_data)
    tarinfo.mtime = time.time()
    tar.addfile(tarinfo, BytesIO(file_data))
    tar.close()
    tar_stream.seek(0)
    return tar_stream


def list_docker_containers(**kwargs):
    return docker_client.containers.list(**kwargs)


def get_container_stats(id_or_name, **kwargs):
    container = docker_client.containers.get(id_or_name)
    return container.stats(**kwargs)


def get_docker_container(container_id):
    return docker_client.containers.get(container_id)
