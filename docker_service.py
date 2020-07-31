import base64
import os
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
from docker import DockerClient
from docker.models.images import Image
from loguru import logger

from config_handler import get_aws_region

ECR_REGISTRY_PATTERN = r"\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/.+"
docker_client = DockerClient.from_env()


class ECRClient:
    client = boto3.client("ecr", region_name=get_aws_region())
    _auth_config = None

    @classmethod
    def auth_config(cls):
        if cls._auth_config is None:
            cls._auth_config = cls._get_auth_config()
        else:
            if datetime.now(timezone.utc) > cls._auth_config["expiresAt"]:
                cls._auth_config = cls._get_auth_config()
        return cls._auth_config

    @classmethod
    def _get_auth_config(cls):
        response = cls.client.get_authorization_token()
        authorization_data = response["authorizationData"][0]
        credentials = base64.b64decode(authorization_data.pop("authorizationToken")).decode().split(":")
        authorization_data["username"] = credentials[0]
        authorization_data["password"] = credentials[1]
        authorization_data["registry"] = urlparse(authorization_data["proxyEndpoint"]).hostname
        return authorization_data


def _pull_docker_image_from_ecr(repository: str, tag: str = None):
    auth = ECRClient.auth_config()
    auth_config = {"username": auth["username"], "password": auth["password"]}
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


def copy_files_from_docker_container(image: Image, docker_path, host_path):
    logger.info("Copy files from {} docker {} to host {}", image.tags, docker_path, host_path)
    container = docker_client.containers.create(image, 'bash')
    filename = os.path.join(host_path, "docker.tar")
    try:
        bits, _ = container.get_archive(f"{docker_path}/.")
        with open(filename, 'wb') as f:
            for chunk in bits:
                f.write(chunk)
        if not os.path.exists(host_path):
            os.makedirs(host_path)
        shutil.unpack_archive(filename, extract_dir=host_path)
    finally:
        logger.info("clean up")
        container.remove()
        if os.path.isfile(filename):
            os.remove(filename)
