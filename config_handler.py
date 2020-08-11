import os
from base64 import urlsafe_b64encode
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from dynaconf import settings

from aws_service import ECRClient
from exceptions import AppError

ecr_client = ECRClient(settings["AWS_REGION"], settings.get("AWS_ACCESS_KEY"), settings.get("AWS_SECRET_KEY"))


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


def get_mongo_config():
    return {
        "mongo_host": required_field_check('MONGO_CONFIG.MONGO_HOST'),
        "mongo_user": required_field_check('MONGO_CONFIG.MONGO_USER'),
        "mongo_pwd": encrpyt_password(required_field_check('MONGO_CONFIG.MONGO_PWD')),
        "mongo_port": required_field_check('MONGO_CONFIG.MONGO_PORT'),
        "mongo_db": required_field_check('MONGO_CONFIG.MONGO_DB'),
    }


def get_ecr_image_list():
    json_file = settings.get('ECR_IMAGE_LIST')
    if not os.path.exists(json_file):
        raise FileNotFoundError(json_file)
    return json.load(open(json_file))


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

