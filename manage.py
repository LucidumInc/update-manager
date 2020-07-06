from loguru import logger

from app.lucidum import update_lucidum, AppError

if __name__ == "__main__":
    try:
        update_lucidum('release-0.0.1.tar.gz')
    except AppError as e:
        logger.exception(e)
    except Exception as e:
        logger.exception("Unhandled exception occurred")
