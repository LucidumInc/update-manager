from dynaconf import settings


def get_archive_config() -> dict:
    return settings["ARCHIVE_CONFIG"]


def get_lucidum_dir() -> str:
    return settings["LUCIDUM_DIR"]


def get_docker_compose_executable() -> str:
    return settings["DOCKER_COMPOSE_EXECUTABLE"]
