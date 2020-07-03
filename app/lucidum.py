import fnmatch
import json
import os
import re
import shutil
import subprocess

import yaml
from docker import DockerClient
from loguru import logger

from app.tmplts import format_template, BaseTemplateFormatter

LUCIDUM_DIR = os.path.join(os.sep, 'home', 'demo', 'lucidum')
DOCKER_COMPOSE_TMPLT_FILE = "docker-compose.yml.jinja2"
RELEASE_FILE = "release.json"



class DockerComposeTemplateFormatter(BaseTemplateFormatter):

    def __init__(self, images: list) -> None:
        super().__init__()
        self._images = images

    @property
    def template_file(self) -> str:
        return DOCKER_COMPOSE_TMPLT_FILE

    @property
    def output_file(self) -> str:
        return os.path.join(LUCIDUM_DIR, 'docker-compose.yml')

    def get_template_params(self):
        return {f"{image['name']}_version": image['version'] for image in self._images}


def docker_load(client: DockerClient, filepath: str) -> list:
    with open(filepath, "rb") as f:
        return client.images.load(f)


def unpack_archive(archive_filepath: str) -> str:
    match = re.match(r"(.+)\.(tar|tar.gz)$", archive_filepath, re.I)
    if not match:
        raise Exception(f"Unsupported archive file format: {archive_filepath}")
    extract_dir = match.group(1)
    logger.info("Unpacking '{}' to '{}' directory...", archive_filepath, extract_dir)
    shutil.unpack_archive(archive_filepath, extract_dir=extract_dir)
    return extract_dir


def load_docker_images(client: DockerClient, release_dir: str) -> None:
    file_pattern = "release-*.tar"
    files = fnmatch.filter(os.listdir(release_dir), file_pattern)
    if not files:
        raise Exception(f"Docker images tar file with '{file_pattern}' pattern is not present")
    tar_filepath = os.path.join(release_dir, files[0])
    logger.info("Loading docker images from {}...", tar_filepath)
    images = docker_load(client, tar_filepath)
    logger.info("Loaded docker images: {}", ", ".join(i.tags[0] for i in images))


def check_release_versions_exist(client: DockerClient, release_images: list) -> None:
    with open(os.path.join("tmplts", DOCKER_COMPOSE_TMPLT_FILE)) as f:
        dc = yaml.full_load(f)
    containers = {
        service["container_name"]: service["image"][0:service["image"].index(":")]
        for service in dc["services"].values()
    }

    docker_images = [tag for image in client.images.list() for tag in image.tags]
    missed_docker_images = []
    for image in release_images:
        docker_image = f"{containers[image['name']]}:{image['version']}"
        if docker_image not in docker_images:
            missed_docker_images.append(docker_image)

    if missed_docker_images:
        raise Exception(f"Missed some release docker images: {', '.join(missed_docker_images)}")


def update_lucidum(archive_filepath: str) -> None:
    release_dir = unpack_archive(archive_filepath)

    client = DockerClient.from_env()
    load_docker_images(client, release_dir)

    with open(os.path.join(release_dir, RELEASE_FILE)) as f:
        release = json.load(f)
    logger.info(f"Release versions:\n{json.dumps(release['images'], indent=2)}")
    check_release_versions_exist(client, release["images"])
    format_template(DockerComposeTemplateFormatter(release["images"]))
    subprocess.run(["/home/demo/anaconda3/bin/docker-compose", "up", "-d"], cwd=LUCIDUM_DIR, check=True)
