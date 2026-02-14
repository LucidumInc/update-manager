import shutil
import subprocess
import os
import uuid
from loguru import logger
from urllib.parse import quote_plus
from exceptions import AppError
from config_handler import get_db_config, get_mongo_config, get_lucidum_dir, get_backup_dir


def run_mongo_backup_or_restore(
    mode: str,
    backup_file: str,
    collection: str | None = None,
    exclude_collections: list[str] | None = None,
    force_table_scan: bool = True,
    stop_web: bool = False,
    web_service: str | None = None,
    name: str | None = None,
    host_dir: str | None = None,
    file_handler=None,
):
    """
    Unified host-side MongoDB backup/restore runner using mongodump/mongorestore.

    This function replaces the old Docker-based workflow. Both backup and restore
    now run directly on the host, which is required for Atlas SRV URIs and also
    simplifies local MongoDB operations.

    Parameters
    ----------
    mode : str
        "backup" or "restore".
    backup_file : str
        Final backup file path (for backup) or existing archive to restore from.
    collection : str | None
        Optional collection to dump (backup only).
    exclude_collections : list[str] | None
        Optional list of collections to exclude from backup.
    force_table_scan : bool
        Whether to add --forceTableScan to mongodump.
    stop_web : bool
        Whether to stop the web service before running.
    web_service : str | None
        Name of the web service to stop/start.
    name : str | None
        Logical name for logging (e.g., "main_db").
    host_dir : str | None
        Directory for temporary dump files (backup only).
    file_handler :
        Object with copy_file(src, dst) for backup copy. If None, shutil.copy2 is used.
    """

    lucidum_dir = get_lucidum_dir()
    docker_executable = shutil.which("docker")

    # ----------------------------------------------------------------------
    # Stop the web service if requested.
    # ----------------------------------------------------------------------
    if stop_web and web_service:
        subprocess.run(
            [docker_executable, "compose", "stop", web_service],
            cwd=lucidum_dir,
            check=True,
        )

    configs = get_mongo_config()
    is_srv = configs["mongo_host"].startswith("mongodb+srv://")
    # URL-encode credentials to avoid breaking the URI when special chars appear.
    encoded_user = quote_plus(configs["mongo_user"])
    encoded_pwd = quote_plus(configs["mongo_pwd"])

    # ----------------------------------------------------------------------
    # Build the MongoDB URI.
    # SRV mode requires mongodb+srv://
    # Local mode uses mongodb:// with explicit port and authSource.
    # ----------------------------------------------------------------------
    if is_srv:
        host_part = configs["mongo_host"].replace("mongodb+srv://", "")
        uri = (
            f"mongodb+srv://{encoded_user}:{encoded_pwd}@{host_part}/"
            f"{configs['mongo_db']}"
        )
    else:
        uri = (
            f"mongodb://{encoded_user}:{encoded_pwd}"
            f"@localhost:{configs['mongo_port']}/{configs['mongo_db']}?"
            f"authSource={configs['mongo_db']}"
        )

    try:
        # ==================================================================
        # BACKUP MODE
        # ==================================================================
        if mode == "backup":
            # Temporary directory for the raw dump archive.
            temp_dir = host_dir or "/usr/lucidum/mongo/db"
            os.makedirs(temp_dir, exist_ok=True)

            # Generate a unique filename to avoid collisions.
            filename = f"{uuid.uuid4()}_mongo_dump.gz"
            temp_path = os.path.join(temp_dir, filename)

            # ------------------------------------------------------------------
            # Build mongodump command.
            # ------------------------------------------------------------------
            cmd = [
                "mongodump",
                f"--uri={uri}",
                f"--archive={temp_path}",
                "--gzip",
            ]

            # Force table scan unless disabled.
            if force_table_scan:
                cmd.append("--forceTableScan")

            # Optional collection-only dump.
            if collection:
                cmd.extend(["--collection", collection])

            # Optional exclusion of specific collections.
            if exclude_collections:
                for col in exclude_collections:
                    cmd.append(f"--excludeCollection={col}")

            logger.info(f"Dumping data for '{name}' into {backup_file} file...")

            # Execute mongodump on the host.
            subprocess.run(cmd, check=True)

            # ------------------------------------------------------------------
            # Copy the temporary dump to the final backup file location.
            # ------------------------------------------------------------------
            if file_handler is not None:
                file_handler.copy_file(temp_path, backup_file)
            else:
                shutil.copy2(temp_path, backup_file)

            full_path = os.path.abspath(backup_file)
            logger.info(f"'{name}' backup data is saved to {full_path}.")

            # Remove only the temporary dump file.
            if os.path.isfile(temp_path):
                os.remove(temp_path)

            return backup_file

        # ==================================================================
        # RESTORE MODE
        # ==================================================================
        elif mode == "restore":
            # Build mongorestore command.
            cmd = [
                "mongorestore",
                "-v",
                f"--uri={uri}",
                f"--archive={backup_file}",
                "--gzip",
                "--drop"  # Always drop before restore.
            ]

            logger.info(f"Restoring MongoDB from backup file {backup_file} ...")
            subprocess.run(cmd, check=True)
            logger.info(f"Restored from {backup_file}.")

        else:
            raise AppError(f"Unknown mode '{mode}'")

    except Exception as e:
        raise AppError(f"Mongo {mode} failed: {e}")

    finally:
        # ------------------------------------------------------------------
        # Restart the web service if it was stopped.
        # ------------------------------------------------------------------
        if stop_web and web_service:
            subprocess.run(
                [docker_executable, "start", web_service],
                cwd=lucidum_dir,
                check=True,
            )
