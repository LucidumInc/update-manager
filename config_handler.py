import base64
from base64 import urlsafe_b64encode
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from docker import DockerClient
from dynaconf import settings

from aws_service import ECRClient
from exceptions import AppError

_docker_client = None


def required_field_check(field):
    v = settings.get(field)
    if v is None:
        raise AppError(f"Config field is required: {field}")
    return v


def encrpyt_password(value, encrypt=False):
    """
    Encrypt or decrypt a string value

    :param value: input value
    :param encrypt: whether to encrypt or decrypt
    :type encrypt: bool
    :return: encrypted or decrypted string
    :rtype: str
    """

    def get_key(fernet):
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(fernet)
        return urlsafe_b64encode(digest.finalize())

    #key = b'pbWkauALYAdtLWQGxUhRuMjxywzN7rba-sdsQGslcy0='
    f = Fernet(get_key(b'data_helper.py'))
    if value is not None and type(value) == str:
        if encrypt:
            return f.encrypt(value.encode()).decode()
        else:
            return f.decrypt(value.encode()).decode()
    else:
        return None


def get_archive_config() -> dict:
    return required_field_check("ARCHIVE_CONFIG")


def get_lucidum_dir() -> str:
    return required_field_check("LUCIDUM_DIR")


def get_ecr_base() -> str:
    return required_field_check("ECR_BASE")


def get_backup_dir() -> str:
    return required_field_check("BACKUP_DIR")


def get_jinja_templates_dir() -> str:
    return required_field_check("JINJA_TEMPLATES_DIR")


def get_docker_compose_tmplt_file() -> str:
    return required_field_check("DOCKER_COMPOSE_TMPLT_FILE")


def get_demo_pwd() -> str:
    return encrpyt_password(required_field_check("DEMO_PWD"))


def get_db_config():
    """Get the db config."""
    return {
        'mysql_host': required_field_check('DATABASE_CONFIG.MYSQL_HOST'),
        'mysql_user': required_field_check('DATABASE_CONFIG.MYSQL_USER'),
        'mysql_pwd': encrpyt_password(required_field_check('DATABASE_CONFIG.MYSQL_PWD')),
        'mysql_port': required_field_check('DATABASE_CONFIG.MYSQL_PORT'),
        'mysql_db': required_field_check('DATABASE_CONFIG.MYSQL_DB'),
    }


def get_aws_config() -> tuple:
    settings.reload()
    return settings.get("AWS_ACCESS_KEY"), settings.get("AWS_SECRET_KEY")


def get_ecr_token() -> str:
    settings.reload()
    return settings.get("ecr_token")


def get_key_dir_config() -> str:
    return settings.get("KEY_DIR", "/usr/lucidum/easy-rsa/keys")


def get_mongo_config():
    return {
        "mongo_host": required_field_check('MONGO_CONFIG.MONGO_HOST'),
        "mongo_user": required_field_check('MONGO_CONFIG.MONGO_USER'),
        "mongo_pwd": encrpyt_password(required_field_check('MONGO_CONFIG.MONGO_PWD')),
        "mongo_port": required_field_check('MONGO_CONFIG.MONGO_PORT'),
        "mongo_db": required_field_check('MONGO_CONFIG.MONGO_DB'),
    }

def get_airflow_db_config():
    return {
        "host": required_field_check('AIRFLOW_DB_CONFIG.HOST'),
        "user": required_field_check('AIRFLOW_DB_CONFIG.USER'),
        "pwd": encrpyt_password(required_field_check('AIRFLOW_DB_CONFIG.PWD')),
        "port": required_field_check('AIRFLOW_DB_CONFIG.PORT'),
        "db": required_field_check('AIRFLOW_DB_CONFIG.DB'),
    }


def get_docker_compose_service_image_mapping_config() -> dict:
    return settings.get("DOCKER_COMPOSE_SERVICE_IMAGE_MAPPING")


def get_airflow_service_image_mapping_config() -> dict:
    return settings.get("AIRFLOW_SERVICE_IMAGE_MAPPING")


def get_ecr_client(access_key: str = None, secret_key: str = None) -> ECRClient:
    return ECRClient(
        settings.get("AWS_REGION", "us-west-1"), access_key, secret_key
    )


def get_docker_client() -> DockerClient:
    global _docker_client
    if _docker_client is None:
        _docker_client = DockerClient.from_env(timeout=600)
    return _docker_client


def get_ecr_image_list():
    return []

def get_images(components):
    ecr_base = get_ecr_base()
    lucidum_base = get_lucidum_dir()
    images = []
    for component in components:
        image_data = {
            'name': component.split(':')[0],
            'version': component.split(':')[-1],
            'image': f'{ecr_base}/{component}'
        }
        image_path = get_image_path_mapping(lucidum_base, image_data['name'], image_data['version'])
        images.append({**image_data, **image_path})
    return images

def get_ecr_images():
    ecr_base = get_ecr_base()
    lucidum_base = get_lucidum_dir()
    ecr_images = {}
    for ecr_image in get_ecr_image_list():
        for version in ecr_image.pop("versions", []):
            image_name = f"{ecr_image['name']}:{version}"
            if image_name in ecr_images:
                continue
            image = ecr_image.copy()
            image["version"] = version
            if "hostPath" in image:
                image["hostPath"] = image["hostPath"].format(
                    base=lucidum_base, component=image["name"], version=version
                )
            if "image" not in image:
                image["image"] = "{}/{}:{}".format(ecr_base, image["name"], version)
            ecr_images[image_name] = image
    return list(ecr_images.values())


def is_connector(image_name):
    return image_name.startswith("connector")


def get_image_path_mapping(lucidum_dir, image_name, image_tag):
    path_mapping = {}
    if is_connector(image_name) or image_name == "action-manager":
        path_mapping["hostPath"] = f"{lucidum_dir}/{image_name}_{image_tag}/external"
        path_mapping["dockerPath"] = "/tmp/app/external"
        path_mapping["hasEnvFile"] = True
    elif image_name == "python/ml":
        path_mapping["hostPath"] = f"{lucidum_dir}/ml_merger_{image_tag}/custom_rules"
        path_mapping["dockerPath"] = "/home/custom_rules"
    return path_mapping


def get_images_from_ecr():
    access_key, secret_key = get_aws_config()
    ecr_client = get_ecr_client(access_key, secret_key)
    lucidum_base = get_lucidum_dir()
    images = []
    for repository in ecr_client.get_repositories():
        for ecr_image in ecr_client.get_images(repository["repositoryName"]):
            for image_tag in ecr_image.get("imageTags", []):
                image = {
                    "name": ecr_image["repositoryName"],
                    "version": image_tag,
                    "image": f"{repository['repositoryUri']}:{image_tag}"
                }
                image.update(get_image_path_mapping(lucidum_base, ecr_image['repositoryName'], image_tag))
                images.append(image)
    return images


def get_local_images():
    docker_client = get_docker_client()
    lucidum_dir = get_lucidum_dir()
    images = []
    for image in docker_client.images.list():
        for imageTag in image.tags:
            data = imageTag.split(":")
            image_data = {
                "name": data[0],
                "version": data[1],
            }
            image_data.update(get_image_path_mapping(lucidum_dir, data[0], data[1]))
            images.append(image_data)
    return images

def get_ecr_pw():
    ecr_token = settings.get('ECR_TOKEN', None)
    if ecr_token:
        credentials = base64.b64decode(ecr_token).decode().split(":")
        if len(credentials) > 1:
            return credentials[1]
    return None

def get_source_mapping_file_path():
    return settings.get('SOURCE_MAPPING_FILE_PATH', '/usr/lucidum/connector*/external/source-mapping.json')

def get_ecr_url():
    return settings.get('ECR_URL', None)
