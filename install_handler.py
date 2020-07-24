import fnmatch
import json
import os
import re
import shutil
import subprocess

import yaml
from docker import DockerClient
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from config_handler import get_archive_config, get_lucidum_dir, get_docker_compose_executable, \
    get_jinja_templates_dir, get_docker_compose_tmplt_file
from exceptions import AppError

_jinja_env = Environment(loader=FileSystemLoader(get_jinja_templates_dir()))


class BaseTemplateFormatter:
    """Represents base formatter for jinja template."""

    @property
    def template_file(self) -> str:
        """Path to jinja template."""
        raise NotImplementedError

    @property
    def output_file(self) -> str:
        """Path to jinja formated file."""
        raise NotImplementedError

    def get_template_params(self):
        """Get parameters for jinja template."""
        raise NotImplementedError


class DockerComposeTemplateFormatter(BaseTemplateFormatter):
    """Represents docker-compose.yml file formatter."""

    def __init__(self, images: list) -> None:
        super().__init__()
        self._images = images

    @property
    def template_file(self) -> str:
        return get_docker_compose_tmplt_file()

    @property
    def output_file(self) -> str:
        return os.path.join(get_lucidum_dir(), 'docker-compose.yml')

    def get_template_params(self):
        with open(os.path.join(get_jinja_templates_dir(), get_docker_compose_tmplt_file())) as f:
            dc = yaml.full_load(f)

        images = {
            service["image"][0:service["image"].index(":")]: service["container_name"]
            for service in dc["services"].values()
        }
        return {f"{images[image['name']]}_version": image['version'] for image in self._images}


def format_template(formatter: BaseTemplateFormatter) -> None:
    """Create formatted file based on jinja template with passed formatter."""
    template = _jinja_env.get_template(formatter.template_file)
    template.stream(**formatter.get_template_params()).dump(formatter.output_file)


def docker_load(client: DockerClient, filepath: str) -> list:
    """Load docker images from given file path."""
    with open(filepath, "rb") as f:
        return client.images.load(f)


def unpack_archive(archive_filepath: str) -> str:
    """Unpack archive from given file path."""
    if not os.path.isfile(archive_filepath):
        raise AppError(f"File '{archive_filepath}' does not exist")
    match = re.match(r"(.+)\.(tar|tar.gz)$", archive_filepath, re.I)
    if not match:
        raise AppError(f"Unsupported archive file format: {archive_filepath}")
    extract_dir = match.group(1)
    logger.info("Unpacking '{}' to '{}' directory...", archive_filepath, extract_dir)
    shutil.unpack_archive(archive_filepath, extract_dir=extract_dir)
    return extract_dir


def load_docker_images(client: DockerClient, release_dir: str) -> None:
    """Find archive based on file pattern and load docker images from it."""
    docker_images_dir = os.path.join(release_dir, get_archive_config()["docker_images_dir"])
    for filename in os.listdir(docker_images_dir):
        if not fnmatch.fnmatch(filename, "*.tar"):
            continue
        f_name = os.path.join(docker_images_dir, filename)
        logger.info("Loading docker images from '{}' file...", f_name)
        images = docker_load(client, f_name)
        logger.info("Loaded docker images from '{}' file: {}", f_name, ", ".join(i.tags[0] for i in images))


def check_release_versions_exist(client: DockerClient, release_images: list) -> None:
    """Check if given release images exist within docker."""
    docker_images = [tag for image in client.images.list() for tag in image.tags]
    missed_docker_images = []
    for image in release_images:
        docker_image = f"{image['name']}:{image['version']}"
        if docker_image not in docker_images:
            missed_docker_images.append(docker_image)

    if missed_docker_images:
        raise AppError(f"Missed some release docker images: {', '.join(missed_docker_images)}")


def format_docker_compose(client: DockerClient, release_dir: str) -> None:
    release_file = os.path.join(release_dir, get_archive_config()["release_file"])
    if not os.path.isfile(release_file):
        raise AppError(f"Release metadata file '{release_file}' does not exist")
    with open(release_file) as f:
        release = json.load(f)
    logger.info(f"Release versions:\n{json.dumps(release['images'], indent=2)}")
    check_release_versions_exist(client, release["images"])
    format_template(DockerComposeTemplateFormatter(release["images"]))


def run_docker_compose() -> None:
    logger.info("Running docker-compose to up lucidum infrastructure...")
    subprocess.run([get_docker_compose_executable(), "up", "-d"], cwd=get_lucidum_dir(), check=True)


def run(archive_filepath: str) -> None:
    """Unpack archive, load docker images, format docker-compose.yml file and run docker-compose."""
    release_dir = unpack_archive(archive_filepath)
    try:
        client = DockerClient.from_env()
        load_docker_images(client, release_dir)
        format_docker_compose(client, release_dir)
        run_docker_compose()
    finally:
        if os.path.isdir(release_dir):
            shutil.rmtree(release_dir)


def install(archive_filepath: str) -> None:
    """Install lucidum from given archive and handle errors."""
    try:
        run(archive_filepath)
    except AppError as e:
        logger.exception(e)
        exit(1)
    except Exception:
        logger.exception("Unhandled exception occurred")
        exit(1)
