from loguru import logger

from app.lucidum import update_lucidum

if __name__ == "__main__":
    try:
        update_lucidum('release-0.0.1.tar.gz')
    except Exception as e:
        logger.exception("Exception occurred")
