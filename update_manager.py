import click
from loguru import logger

logger.add("logs/job_{time}.log", rotation="1 day", retention="30 days", diagnose=True)

@click.group()
def cli():
    pass

@cli.command()
@click.option(
    '--archive','-a', required=True, type=click.Path(exists=True, dir_okay=False),
    help="Archive filepath to use for lucidum installation"
)
def install(archive: str) -> None:
    from install_handler import install as setup_lucidum
    setup_lucidum(archive)

@cli.command()
@click.option('--component','-c', multiple=True, type=click.Choice(['python/ml', 'mvp1_backend']))
def installecr(component) -> None:
    logger.info(component)


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
