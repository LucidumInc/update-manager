import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from config_handler import get_archive_config, get_lucidum_dir, get_jinja_templates_dir, \
    get_docker_compose_tmplt_file, get_ecr_images
from docker_service import load_docker_images, pull_docker_image, docker_client, copy_files_from_docker_container
from exceptions import AppError

_jinja_env = Environment(loader=FileSystemLoader(get_jinja_templates_dir()))


class BaseTemplateFormatter:
    """Represents base formatter for jinja template."""

    def __init__(self) -> None:
        self._template_file = None
        self._output_file = None
        self._template_params = None

    @property
    def template_file(self) -> str:
        """Path to jinja template."""
        raise NotImplementedError

    @property
    def output_file(self) -> str:
        """Path to jinja formated file."""
        raise NotImplementedError

    @property
    def template_params(self):
        """Get parameters for jinja template."""
        raise NotImplementedError


class DockerComposeTemplateFormatter(BaseTemplateFormatter):
    """Represents docker-compose.yml file formatter."""

    def __init__(self, images: list) -> None:
        super().__init__()
        self._images = images

    @property
    def template_file(self) -> str:
        if not self._template_file:
            self._template_file = get_docker_compose_tmplt_file()
        return self._template_file

    @property
    def output_file(self) -> str:
        if not self._output_file:
            self._output_file = os.path.join(get_lucidum_dir(), 'docker-compose.yml')
        return self._output_file

    @property
    def template_params(self):
        if not self._template_params:
            with open(os.path.join(get_jinja_templates_dir(), get_docker_compose_tmplt_file())) as f:
                dc = yaml.full_load(f)
            images = {
                service["image"][0:service["image"].index(":")]: service["container_name"]
                for service in dc["services"].values()
            }
            self._template_params = {images[image['name']]: image['version'] for image in self._images}
        return self._template_params


def format_template(formatter: BaseTemplateFormatter) -> None:
    """Create formatted file based on jinja template with passed formatter."""
    template = _jinja_env.get_template(formatter.template_file)
    template.stream(**formatter.template_params).dump(formatter.output_file)


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


def load_docker_images_from_file(release_dir: str) -> None:
    """Find archive based on file pattern and load docker images from it."""
    docker_images_dir = os.path.join(release_dir, get_archive_config()["docker_images_dir"])
    for filename in os.listdir(docker_images_dir):
        if not fnmatch.fnmatch(filename, "*.tar"):
            continue
        f_name = os.path.join(docker_images_dir, filename)
        logger.info("Loading docker images from '{}' file...", f_name)
        images = load_docker_images(f_name)
        logger.info("Loaded docker images from '{}' file: {}", f_name, ", ".join(i.tags[0] for i in images))


def check_release_versions_exist(release_images: list) -> None:
    """Check if given release images exist within docker."""
    docker_images = [tag for image in docker_client.images.list() for tag in image.tags]
    missed_docker_images = []
    for image in release_images:
        docker_image = f"{image['name']}:{image['version']}"
        if docker_image not in docker_images:
            missed_docker_images.append(docker_image)

    if missed_docker_images:
        raise AppError(f"Missed some release docker images: {', '.join(missed_docker_images)}")


def format_docker_compose(images: list):
    # logger.info(f"Release versions:\n{json.dumps(images, indent=2)}")
    check_release_versions_exist(images)
    formatter = DockerComposeTemplateFormatter(images)
    format_template(formatter)
    return formatter


def run_docker_compose() -> None:
    logger.info("Running docker-compose to up lucidum infrastructure...")
    subprocess.run([shutil.which("docker-compose"), "up", "-d"], cwd=get_lucidum_dir(), check=True)


def run_docker_compose_restart(container: str):
    logger.info("Restarting '{}' container...", container)
    subprocess.run([shutil.which("docker-compose"), "restart", container], cwd=get_lucidum_dir(), check=True)


def update_docker_image(image_data, copy_default):
    logger.info(image_data)
    image_tag = f"{image_data['name']}:{image_data['version']}"
    _remove_image(image_data['image'])
    _remove_image(image_tag)
    image = pull_docker_image(image_data["image"])
    logger.info(f"Updated to latest image, id: {image.short_id} tag: {image.tags}")
    image.tag(image_tag)
    docker_client.images.remove(image_data['image'])
    image.reload()
    host_path, docker_path = image_data.get("hostPath"), image_data.get("dockerPath")
    if host_path:
        _check_path(host_path)
    if copy_default and docker_path and host_path:
        copy_files_from_docker_container(image, docker_path, host_path)
    has_env_file = image_data.get("hasEnvFile")
    if has_env_file:
        os.link(os.path.join("resources", "connector_env_file"), os.path.join(host_path, ".env"))


@logger.catch(onerror=lambda _: sys.exit(1))
def install(archive_filepath: str) -> None:
    """Unpack archive, load docker images, format docker-compose.yml file and run docker-compose."""
    release_dir = unpack_archive(archive_filepath)
    try:
        load_docker_images_from_file(release_dir)
        release_file = os.path.join(release_dir, get_archive_config()["release_file"])
        if not os.path.isfile(release_file):
            raise AppError(f"Release metadata file '{release_file}' does not exist")
        with open(release_file) as f:
            data = json.load(f)
        format_docker_compose(data["images"])
        run_docker_compose()
    except AppError as e:
        logger.exception(e)
        sys.exit(1)
    finally:
        if os.path.isdir(release_dir):
            shutil.rmtree(release_dir)

# ---------- install ecr adhoc code ----------


def get_install_ecr_components():
    ecr_images = get_ecr_images()
    result = []
    for ecr_image in ecr_images:
        result.append(ecr_image["name"])
    return result


@logger.catch(onerror=lambda _: sys.exit(1))
def install_ecr(components, copy_default, restart):
    ecr_images = get_ecr_images()
    for ecr_image in ecr_images:
        if ecr_image["name"] not in components:
            continue
        update_docker_image(ecr_image, copy_default)
    if restart and "mvp1_backend" in components:
        run_docker_compose_restart("web")


def _remove_image(image_name):
    result = docker_client.images.list(image_name)
    if result:
        docker_client.images.remove(image_name, True)


def _check_path(path):
    if not os.path.exists(path):
        os.makedirs(path)

