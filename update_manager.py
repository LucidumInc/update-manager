import click
from loguru import logger

from config_handler import get_images_from_ecr
from install_handler import install_ecr, get_install_ecr_components
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
@click.option('--components', '-c', required=True, multiple=True, type=click.Choice(get_install_ecr_components()), help="ecr component list")
@click.option('--copy-default', '-d', default=False, is_flag=True, help='copy default files from docker to host')
@click.option('--restart', '-r', is_flag=True, help='restart web container')
def installecr(components, copy_default, restart) -> None:
    logger.info(f"ecr components: {components}")
    install_ecr(components, copy_default, restart)


@cli.command()
@click.option(
    '--components', '-c', required=True, multiple=True,
    type=click.Choice(get_install_ecr_components(get_images=get_images_from_ecr)), help="ecr component list"
)
@click.option('--copy-default', '-d', default=False, is_flag=True, help='copy default files from docker to host')
@click.option('--restart', '-r', is_flag=True, help='restart web container')
@click.option('--install', '-i', is_flag=True, help='install components')
def ecr(components, copy_default, restart, install):
    logger.info(f"ecr components: {components}")
    if install:
        install_ecr(components, copy_default, restart, get_images=get_images_from_ecr)


@cli.command()
def init() -> None:
    from init_handler import init as init_lucidum
    init_lucidum()


@cli.command()
@click.option(
    '--component', '-c', required=True,
    type=click.Choice(get_install_ecr_components(lambda i: i.get("hasEnvFile"))), help="ecr component"
)
@click.option('--cmd', help="command to run inside component")
def docker_run(component: str, cmd: str) -> None:
    from docker_run_handler import run
    run(component, cmd)


@cli.command()
@click.option("--data", "-d", multiple=True, type=click.Choice(['mysql', 'mongo', 'lucidum']))
def backup(data: tuple):
    from backup_handler import backup as backup_lucidum
    backup_data = [d for d in data]
    if not backup_data:
        backup_data = ["lucidum"]
    backup_lucidum(backup_data)


@cli.command()
@click.option("--data", "-d", multiple=True, required=True, type=(str, click.Path(exists=True, dir_okay=False)))
def restore(data):
    from restore_handler import restore as restore_lucidum
    restore_lucidum([d for d in data])


if __name__ == '__main__':
    cli()
