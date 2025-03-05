import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

import yaml
from docker.errors import APIError
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from tabulate import tabulate

from config_handler import get_archive_config, get_lucidum_dir, get_jinja_templates_dir, \
    get_docker_compose_tmplt_file, get_ecr_images, get_images_from_ecr, get_local_images, \
    get_docker_compose_service_image_mapping_config, get_airflow_service_image_mapping_config
from docker_service import load_docker_images, pull_docker_image, copy_files_from_docker_container, \
    remove_docker_image, list_docker_images, get_docker_image, stop_docker_compose_service
from exceptions import AppError

_jinja_env = Environment(loader=FileSystemLoader(get_jinja_templates_dir()))

# all service to image mapping should be here in order to be updated
DOCKER_COMPOSE_SERVICE_IMAGE_MAPPING = {
    "web": "mvp1_backend",
    "connector-api": "connector-api",
    "action-manager": "action-manager",
    "global-manager": "global-manager",
    "nginx": "nginx",
}

# airflow only if image name is different from service name
AIRFLOW_SERVICE_IMAGE_MAPPING = {
    "merger": "python/ml",
}


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
    docker_images = [tag for image in list_docker_images() for tag in image.tags]
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
    subprocess.run(
        [shutil.which("docker-compose"), "up", "-d"], cwd=get_lucidum_dir(), input=b"y", check=True
    )


def run_docker_compose_restart(container: str):
    logger.info("Restarting '{}' container...", container)
    lucidum_dir = get_lucidum_dir()
    subprocess.run([shutil.which("docker-compose"), "rm", "-f", "-s", "-v", container], cwd=lucidum_dir, check=True)
    subprocess.run([shutil.which("docker-compose"), "up", "-d"], cwd=lucidum_dir, check=True)


def restart_docker_compose_services():
    logger.info("Restarting docker-compose services...")
    lucidum_dir = get_lucidum_dir()
    try:
        subprocess.run([shutil.which("docker-compose"), "down"], cwd=lucidum_dir, check=True)
    except:
        logger.error('docker-compose down error')
    finally:
        subprocess.run([shutil.which("docker-compose"), "up", "-d"], cwd=lucidum_dir, check=True)


def create_hard_link(src, dst):
    if os.path.exists(dst):
        return
    os.link(src, dst)


class DockerImagesUpdater:

    def __init__(self, ecr_images, copy_default, restart) -> None:
        self._ecr_images = ecr_images
        self._copy_default = copy_default
        self._restart = restart
        self._images_to_remove = []

    def _update_image(self, image_data):
        image_tag = f"{image_data['name']}:{image_data['version']}"
        try:
            old_image = get_docker_image(image_tag)
        except:
            logger.info(f'{image_tag} local image does not exist!')
            old_image = None
        image = pull_docker_image(image_data["image"])
        logger.info(f"Updated to latest image, id: {image.short_id} tag: {image.tags}")
        if old_image and image.short_id != old_image.short_id:
            self._images_to_remove.append(old_image.short_id)
        image.tag(image_tag)
        image.reload()
        self._images_to_remove.append(image_data["image"])
        host_path, docker_path = image_data.get("hostPath"), image_data.get("dockerPath")
        if self._copy_default and docker_path and host_path:
            copy_files_from_docker_container(image, docker_path, host_path)

    def restart(self) -> None:
        components = [component["name"] for component in self._ecr_images]
        if (self._restart and "mvp1_backend" in components) or \
                (self._restart and any("connector-" in component for component in components)):
            restart_docker_compose_services()

    def __call__(self):
        for ecr_image in self._ecr_images:
            self._update_image(ecr_image)
        self.restart()
        for image in self._images_to_remove:
            try:
                remove_docker_image(image, force=True)
            except APIError as e:
                logger.warning(e)


def _get_service_by_image(mapping: dict, image_name: str) -> str:
    for service, image in mapping.items():
        if image == image_name:
            return service


def update_docker_compose_file(components: list) -> None:
    lucidum_dir = get_lucidum_dir()
    docker_compose_file_path = os.path.join(lucidum_dir, "docker-compose.yml")
    if not os.path.isfile(docker_compose_file_path):
        logger.warning("'{}' file does not exist", docker_compose_file_path)
        return
    with open(docker_compose_file_path) as f:
        data = yaml.full_load(f)
    mapping = get_docker_compose_service_image_mapping_config() or DOCKER_COMPOSE_SERVICE_IMAGE_MAPPING
    for component in components:
        service = _get_service_by_image(mapping, component["name"])
        if service is None:
            continue
        if service not in data["services"]:
            logger.warning("'{}' service not found in docker compose file", service)
            continue
        data["services"][service]["image"] = f"{component['name']}:{component['version']}"
    with open(docker_compose_file_path, "w") as f:
        yaml.dump(data, f)


def update_airflow_settings_file(components: list) -> None:
    lucidum_dir = get_lucidum_dir()
    airflow_settings_file_path = os.path.join(lucidum_dir, "airflow", "dags", "settings.yml")
    if not os.path.isfile(airflow_settings_file_path):
        logger.warning("'{}' file does not exist", airflow_settings_file_path)
        return
    with open(airflow_settings_file_path) as f:
        data = yaml.full_load(f)
    mapping = get_airflow_service_image_mapping_config() or AIRFLOW_SERVICE_IMAGE_MAPPING
    for component in components:
        service = _get_service_by_image(mapping, component["name"])
        if service is not None:
            if service not in data["global"]:
                logger.warning("'{}' service not found in airflow settings file", service)
                continue
            data["global"][service]["version"] = component["version"]
        elif component["name"].startswith("connector"):
            connector_type = component["name"].split("-", 1)[-1]
            if "connectors" not in data["global"]:
                logger.warning("No connectors found in airflow settings file")
                continue
            if connector_type not in data["global"]["connectors"]:
                logger.warning("'{}' service not found in airflow settings file", component["name"])
                continue
            data["global"]["connectors"][connector_type]["version"] = component["version"]
        else:
            if component["name"] not in data["global"]:
                logger.warning("'{}' service not found in airflow settings file", component["name"])
                continue
            data["global"][component["name"]]["version"] = component["version"]
    with open(airflow_settings_file_path, "w") as f:
        yaml.dump(data, f)


class DockerImagesUpdaterWithNewRestart(DockerImagesUpdater):

    def __init__(self, ecr_images, copy_default, restart, update_files=False) -> None:
        super().__init__(ecr_images, copy_default, restart)
        self.update_files = update_files

    def restart(self) -> None:
        if self.update_files or self._restart:
            lucidum_dir = get_lucidum_dir()
            docker_compose_file_path = os.path.join(lucidum_dir, "docker-compose.yml")
            docker_compose_data = None
            if os.path.isfile(docker_compose_file_path):
                with open(docker_compose_file_path) as f:
                    docker_compose_data = yaml.full_load(f)
            mapping = get_docker_compose_service_image_mapping_config() or DOCKER_COMPOSE_SERVICE_IMAGE_MAPPING
            for component in self._ecr_images:
                service = _get_service_by_image(mapping, component["name"])
                if service is None:
                    continue
                if docker_compose_data is not None:
                    if service in docker_compose_data["services"]:
                        stop_docker_compose_service(lucidum_dir, service)
                image_tag = f"{component['name']}:{component['version']}"
                try:
                    remove_docker_image(image_tag, force=True)
                except APIError as e:
                    logger.warning(e)
                image = pull_docker_image(component["image"])
                image.tag(image_tag)
                image.reload()
            if self.update_files:
                update_docker_compose_file(self._ecr_images)
                update_airflow_settings_file(self._ecr_images)
            run_docker_compose()


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


def get_components(filter_=None, get_images=get_ecr_images):
    ecr_images = get_images()
    filter_images = filter_
    if not filter_images:
        filter_images = lambda i: True
    return [
        f"{ecr_image['name']}:{ecr_image['version']}" for ecr_image in ecr_images if filter_images(ecr_image)
    ]


@logger.catch(onerror=lambda _: sys.exit(1))
def install_ecr(components, copy_default, restart, get_images=get_ecr_images):
    ecr_images = get_images()
    update_docker_images = DockerImagesUpdater(
        [image for image in ecr_images if f"{image['name']}:{image['version']}" in components], copy_default, restart
    )
    update_docker_images()

@logger.catch(onerror=lambda _: sys.exit(1))
def install_image_from_ecr(images, copy_default, restart, update_files=False):
    update_docker_images = DockerImagesUpdaterWithNewRestart(images, copy_default, restart, update_files)
    update_docker_images()

@logger.catch(onerror=lambda _: sys.exit(1))
def remove_components(components):
    lucidum_dir = get_lucidum_dir()
    images = get_local_images()
    for image in images:
        component = f"{image['name']}:{image['version']}"
        if component not in components:
            continue
        host_path = image.get("hostPath")
        if host_path and os.path.exists(host_path) and os.path.isdir(host_path):
            archive_dir = os.path.join(lucidum_dir, "archive")
            rel_path = host_path.split(f'{lucidum_dir}/')[-1]
            copy_rel_path = f"{rel_path}_{datetime.now().strftime('%m-%d-%Y_%H_%M_%S')}"
            copy_path = os.path.join(archive_dir, copy_rel_path)
            logger.info("Copying '{}' directory to '{}' directory...", host_path, copy_path)
            shutil.copytree(host_path, copy_path)
            rm_path = os.path.join(lucidum_dir, rel_path.split("/")[0])
            logger.info("Removing '{}' directory...", rm_path)
            shutil.rmtree(rm_path)
        result = list_docker_images(name=component)
        if result:
            remove_docker_image(component, force=True)


def get_ecr_to_local_components_conjunction() -> list:
    local_images = get_local_images()
    ecr_images = get_images_from_ecr()

    result = {}
    for image in ecr_images:
        component = f"{image['name']}:{image['version']}"
        host_path = image.get("hostPath")
        result[component] = {
            "ecr_image": component,
            "local_image": None,
            "host_path": host_path if host_path and os.path.exists(host_path) else None
        }

    for image in local_images:
        component = f"{image['name']}:{image['version']}"
        host_path = image.get("hostPath")
        host_path = host_path if host_path and os.path.exists(host_path) else None
        if component in result:
            result[component]["local_image"] = component
            result[component]["host_path"] = result[component]["host_path"] or host_path
        else:
            result[component] = {
                "ecr_image": None,
                "local_image": component,
                "host_path": host_path
            }

    return list(result.values())


@logger.catch(onerror=lambda _: sys.exit(1))
def list_components():
    components = get_ecr_to_local_components_conjunction()

    print(tabulate(
        [[c["ecr_image"], c["local_image"], c["host_path"]] for c in components],
        headers=["ECR Image", "Local Image", "Local Folder"], tablefmt="orgtbl", missingval="na"
    ))


def _check_path(path):
    if not os.path.exists(path):
        os.makedirs(path)

def get_image_and_version():
    lucidum_dir = get_lucidum_dir()
    result = []
    docker_compose_file_path = os.path.join(lucidum_dir, "docker-compose.yml")
    if not os.path.isfile(docker_compose_file_path):
        logger.warning("'{}' file does not exist", docker_compose_file_path)
        return result
    with open(docker_compose_file_path) as f:
        data = yaml.full_load(f)
        logger.info(data)
        for service, value in data.get('services', {}).items():
            result.append(value['image'])

    airflow_settings_file_path = os.path.join(lucidum_dir, "airflow", "dags", "settings.yml")
    if not os.path.isfile(airflow_settings_file_path):
        logger.warning("'{}' file does not exist", airflow_settings_file_path)
        return result
    with open(airflow_settings_file_path) as f:
        data = yaml.full_load(f)
        logger.info(data)
        result.append(f"action-manager:{data['global']['action-manager']['version']}")
        result.append(f"python/ml:{data['global']['merger']['version']}")
        for type, value in data['global']['connectors'].items():
            result.append(f"connector-{type}:{value['version']}")
    return [*set(result)]
