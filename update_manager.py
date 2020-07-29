import click
from loguru import logger
from install_handler import install_ecr, get_install_ecr_components
logger.add("logs/job_{time}.log", rotation="1 day", retention="30 days", diagnose=True)

@click.group()
def cli():
    pass

@cli.command()
@click.option(
    '--archive', '-a', type=click.Path(exists=True, dir_okay=False),
    help="Archive filepath to use for lucidum installation"
)
@click.option("--json-file", "-j", type=click.Path(exists=True, dir_okay=False))
@click.option("--copy-default", "-d", default=False, is_flag=True, help='copy default files from docker to host')
@click.option(
    '--components', '-c', multiple=True, help="ecr component list"
)
def install(archive: str, json_file: str, copy_default: bool, components: tuple) -> None:
    if archive is not None:
        from install_handler import install as install_archive
        install_archive(archive)
    elif json_file is not None:
        from install_handler import update
        update(json_file, copy_default, components)
    else:
        raise Exception("Option ('--archive' or '--json-file') must be specified")

@cli.command()
@click.option('--components','-c', required=True, multiple=True, type=click.Choice(get_install_ecr_components()), help="ecr component list")
@click.option('--copy_default', '-d', default=False, help='copy default files from docker to host')
def installecr(components, copy_default) -> None:
    logger.info(f"ecr components: {components}")
    install_ecr(components, copy_default)


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
