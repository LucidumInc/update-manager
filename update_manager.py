import click
import json
from loguru import logger

from config_handler import get_images_from_ecr, get_local_images, get_images, get_key_dir_config, encrpyt_password
from history_handler import history_command, get_install_ecr_entries, get_history_command_choices
from install_handler import install_ecr, get_components, remove_components, list_components, install_image_from_ecr

logger.add("logs/job_{time}.log", rotation="1 day", retention="30 days", diagnose=True)


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    '--archive', '-a', required=True, type=click.Path(exists=True, dir_okay=False),
    help="Archive filepath to use for lucidum installation"
)
def install(archive: str) -> None:
    from install_handler import install as install_archive
    install_archive(archive)


@cli.command()
@click.option('--components', '-c', required=True, multiple=True, help="install docker images from ecr")
@click.option('--copy-default', '-d', default=False, is_flag=True, help='copy default files from docker to host')
@click.option('--restart', '-r', is_flag=True, help='restart components')
@click.option('--update-files', '-u', default=False, is_flag=True, help='update files with components versions')
def installecr(components, copy_default, restart, update_files) -> None:
    logger.info(f"ecr components: {components}, copy default: {copy_default}, restart: {restart}")
    images = get_images(components)
    logger.info(json.dumps(images, indent=2))
    install_image_from_ecr(images, copy_default, restart, update_files)


@cli.command()
@click.option('--components', '-c', multiple=True, help="ecr component list")
@click.option('--copy-default', '-d', default=False, is_flag=True, help='copy default files from docker to host')
@click.option('--restart', '-r', default=False, is_flag=True, help='restart web container')
@click.option('--list', '-l', 'list_', is_flag=True, help='list available components')
# @history_command(command="ecr", get_history_entries=get_install_ecr_entries, get_images=get_images_from_ecr)
def ecr(components, copy_default, restart, list_):
    if list_:
        list_components()
    else:
        logger.info(f"ecr components: {components}, copy default: {copy_default}, restart: {restart}")
        install_ecr(components, copy_default, restart, get_images=get_images_from_ecr)


@cli.command()
@click.option(
    '--components', '-c', required=True, multiple=True,
    type=click.Choice(get_components(get_images=get_local_images)), help="component list"
)
def remove(components):
    logger.info("Components to remove: {}", components)
    remove_components(components)


@cli.command()
def init() -> None:
    from init_handler import init as init_lucidum
    init_lucidum()


@cli.command()
@click.option(
    '--component', '-c', required=True,
    type=click.Choice(get_components(filter_=lambda i: i.get("hasEnvFile"), get_images=get_local_images)),
    help="ecr component"
)
@click.option('--cmd', required=True, help="command to run inside component")
def docker_run(component: str, cmd: str) -> None:
    from docker_run_handler import run
    run(component, cmd)


@cli.command()
@click.option("--command", "-c", type=click.Choice(get_history_command_choices()),
              help="command to retrieve history for")
def history(command: str):
    from history_handler import run
    run(command)


@cli.command()
@click.option("--output", "-o", required=True, type=click.Choice(["mongo"]), help="data source")
def connector(output: str):
    from connector_handler import run
    run(output)


@cli.command(name="import")
@click.option("--db", required=True, type=click.Choice(["mongo"]), help="database where data should be imported in")
@click.option("--source", required=True, type=click.Path(exists=True, dir_okay=False),
              help="filepath which contains actual data")
@click.option("--destination", required=True, type=str, help="destination where data should be imported in")
def import_(db, source, destination):
    from import_handler import run
    run(db, source, destination)


@cli.command()
@click.option("--data", "-d", multiple=True, default=["lucidum"], type=click.Choice(['mysql', 'mongo', 'lucidum']))
@click.option("--filepath", "-f", type=click.Path())
@click.option("--include-collection", "-i")
@click.option("--exclude-collection", "-e", multiple=True)
def backup(data: tuple, filepath: str, include_collection: str = None, exclude_collection: tuple = None):
    from backup_handler import backup as backup_lucidum
    backup_lucidum(list(data), filepath, include_collection, list(exclude_collection))


@cli.command()
def migrate_vod():
    """
    Migrate VOD related mongo collections.
    Place json files under /usr/lucidum/mongo/db folder
    """
    import socket
    from handlers.mongo_import import run
    hostname = ""
    try:
        hostname = socket.gethostname()
    except socket.error as e:
        logger.warning(f'get hostname error: {e}')
    logger.info(f"====> dashboard and chart import for {hostname}")
    run('postReport.json', 'biQuery_lucidum_report', drop=True)
    run('postDashboard.json', 'biQuery_lucidum_dashboard', drop=True)
    if hostname.lower() == 'demo':
        logger.info("====> Bypass demo for smart label and saved query import")
    else:
        logger.info(f"====> smart label and saved query import for {hostname}")
        run('postDynamicFieldDef.json', 'smart_label', override=True, upsert_fields='field_name')
        run('postDynamicFieldDisplay.json', 'field_display_local', override=True, upsert_fields='field_name')
        run('postSavedQuery.json', 'Query_Builder', override=True, upsert_fields='name')
        

@cli.command()
@click.option('--customer-name', required=True, help="customer name")
def migrate_extra(customer_name: str):
    """
    Migrate extra mongo collections.
    Place json files under /usr/lucidum/mongo/db folder
    """
    from handlers.mongo_import import run
    run(f'postDynamicFieldDef[{customer_name}].json', 'smart_label', override=True,
        upsert_fields='field_name,created_by', cleanup=False)
    run(f'postDynamicFieldDisplay[{customer_name}].json', 'field_display_local', override=True,
        upsert_fields='field_name', cleanup=False)
    run(f'postActionConfig[{customer_name}].json', 'local_integration_configuration', override=True,
        upsert_fields='bridge_name,config_name', cleanup=False)
    run(f'postActionSchedule[{customer_name}].json', 'action_schedule', override=True,
        upsert_fields='query_name,create_by', cleanup=False)


@cli.command()
def update_action_config():
    """
    Update Action Config in mongo.
    Place json files under /usr/lucidum/mongo/db folder
    """
    from handlers.mongo_import import run
    run('emailActionConfig.json', 'local_integration_configuration', override=True,
        upsert_fields='bridge_name,config_name')


@cli.command()
@click.option("--data", "-d", multiple=True, required=True, type=(str, click.Path(dir_okay=False)))
def restore(data):
    from restore_handler import restore as restore_lucidum
    restore_lucidum(list(data))


@cli.command()
@click.option(
    "--key-dir", "-d", required=False, default=get_key_dir_config(), type=click.Path(exists=True, file_okay=False)
)
def build_ca(key_dir: str) -> None:
    from rsa import build_ca as build_ca_
    build_ca_(key_dir=key_dir)


@cli.command()
@click.option("--name", "-n", required=True, type=str)
@click.option(
    "--key-dir", "-d", required=False, default=get_key_dir_config(), type=click.Path(exists=True, file_okay=False)
)
def build_key_server(name: str, key_dir: str) -> None:
    from rsa import build_key_server as build_key_server_
    build_key_server_(name, key_dir=key_dir)


@cli.command()
@click.option("--name", "-n", required=True, type=str)
@click.option(
    "--key-dir", "-d", required=False, default=get_key_dir_config(), type=click.Path(exists=True, file_okay=False)
)
def build_key_client(name: str, key_dir: str) -> None:
    from rsa import build_key_client as build_key_client_
    build_key_client_(name, key_dir=key_dir)


@cli.command()
@click.option(
    "--key-dir", "-d", required=False, default=get_key_dir_config(), type=click.Path(exists=True, file_okay=False)
)
def build_dh(key_dir: str) -> None:
    from rsa import build_dh as build_dh_
    build_dh_(key_dir=key_dir)


@cli.command()
def run_connector_config_to_db():
    from api_handler import get_local_connectors, get_local_action, env_vars
    from docker_service import run_docker_container
    connectors = get_local_connectors()
    action = get_local_action()
    if action:
        connectors.append(action)
    for connector in connectors:
        try:
            if connector['type'] == 'action':
                main_image = "action-manager"
            else:
                main_image = f"connector-{connector['type']}"
            image = f"{main_image}:{connector['version']}"
            command = f'bash -c "python lucidum_{connector["type"]}.py config-to-db"'
            out = run_docker_container(
                image, stdout=True, stderr=True, remove=True, network="lucidum_default", command=command,
                environment=env_vars
            )
            logger.info(connector)
            logger.info(out.decode())
        except Exception as e:
            logger.warning(f"config-to-db error: {e}")


@cli.command()
def df_to_sl():
    logger.info("nothing to do here.")


@cli.command()
def run_connector_test():
    from helper import run_connector_profile_test
    run_connector_profile_test()


@cli.command()
def run_action_test():
    from helper import run_action_config_test
    run_action_config_test()


if __name__ == '__main__':
    cli()
