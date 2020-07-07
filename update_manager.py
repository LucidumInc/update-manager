import click


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


if __name__ == '__main__':
    cli()
