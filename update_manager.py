import click
from loguru import logger

from config_handler import get_images_from_ecr, get_local_images
from history_handler import history_command, get_install_ecr_entries, get_history_command_choices
from install_handler import install_ecr, get_components, remove_components, list_components
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
@click.option('--components', '-c', required=True, multiple=True, type=click.Choice(get_components()), help="ecr component list")
@click.option('--copy-default', '-d', default=False, is_flag=True, help='copy default files from docker to host')
@click.option('--restart', '-r', is_flag=True, help='restart web container')
def installecr(components, copy_default, restart) -> None:
    logger.info(f"ecr components: {components}")
    install_ecr(components, copy_default, restart)


@cli.command()
@click.option(
    '--components', '-c', multiple=True,
    type=click.Choice(get_components(get_images=get_images_from_ecr)), help="ecr component list"
)
@click.option('--copy-default', '-d', default=False, is_flag=True, help='copy default files from docker to host')
@click.option('--restart', '-r', default=False, is_flag=True, help='restart web container')
@click.option('--list', '-l', 'list_', is_flag=True, help='list available components')
@history_command(command="ecr", get_history_entries=get_install_ecr_entries, get_images=get_images_from_ecr)
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
@click.option("--command", "-c", type=click.Choice(get_history_command_choices()), help="command to retrieve history for")
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
@click.option("--source", required=True, type=click.Path(exists=True, dir_okay=False), help="filepath which contains actual data")
@click.option("--destination", required=True, type=str, help="destination where data should be imported in")
def import_(db, source, destination):
    from import_handler import run
    run(db, source, destination)


@cli.command()
@click.option("--data", "-d", multiple=True, default=["lucidum"], type=click.Choice(['mysql', 'mongo', 'lucidum']))
@click.option("--filepath", "-f", type=click.Path(dir_okay=False))
def backup(data: tuple, filepath: str):
    from backup_handler import backup as backup_lucidum
    backup_lucidum(list(data), filepath)


@cli.command()
@click.option("--data", "-d", multiple=True, required=True, type=(str, click.Path(dir_okay=False)))
def restore(data):
    from restore_handler import restore as restore_lucidum
    restore_lucidum(list(data))


if __name__ == '__main__':
    cli()
