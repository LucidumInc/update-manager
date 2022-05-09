# update manager

update manager update local docker images by pulling the latest docker
images from ECR or from latest install package file

## Initialize lucidum folder
Create lucidum folder based on path given in DYNACONF_LUCIDUM_DIR environment variable:

```shell script
$ python update_manager.py init
```

## Install lucidum components based on local config

```shell script
$ python update_manager.py installecr [OPTIONS]
```

Options:

- `-c, --components`: components that should be installed [required]
- `-d, --copy-default`: copy content of connectors external folder to host machine [not required]
- `-r, --restart`: restart web container. It will work only if
  mvp1_backend component is passed [not required]
- `--help`: document this command with list of available components [not
  required]

## Install lucidum components from ECR

```shell script
$ python update_manager.py ecr [OPTIONS]
```

Options:

- `-c, --components`: components that should be installed [not required]
- `-d, --copy-default`: copy content of connectors external folder to host machine [not required]
- `-r, --restart`: restart web container. It will work only if
  mvp1_backend component is passed [not required]
- `-l, --list`: list all components from ECR registry paired with
  locally installed components using table view [not required]
- `--help`: document this command with list of available components
  [not required]

## Remove lucidum components

```shell script
$ python update_manager.py remove [OPTIONS]
```

Options:

- `-c, --components`: components that should be removed [required]
- `--help`: document this command with list of available components
  [not required]

## Run command within lucidum component

```shell script
$ python update_manager.py docker-run [OPTIONS]
```

Options:

- `-c, --component`: component to use for running command (--cmd) [required]
- `--cmd`: command to run within component [required]
- `--help`: document this command with list of available components [not required]

## List command history

```shell script
$ python update_manager.py history [OPTIONS]
```

Options:

- `-c, --command`: name of command to get history for [required]
- `--help`: document this command with list of commands with history [not required]

## Write local connector and bridge information to data source

```shell script
$ python update_manager.py connector [OPTIONS]
```

Options:

- `-o, --output`: data source [required]
- `--help`: document this command with list of available data sources [not required]

## Setup lucidum folder

```shell
cp resources/docker-compose_file ../docker-compose.yml\
cp resources/env_file ../.env\
mkdir -p ../mongo/db\
chmod -R 770 ../mongo\
mkdir -p ../mysql/config\
mkdir -p ../mysql/db\
chmod -R 770 ../mysql\
mkdir -p ../web/app/hostdata\
mkdir -p ../web/app/logs\
chmod -R 770 ../web

sudo mkdir -p /usr/lucidum_backup\
sudo chown -R demo:demo /usr/lucidum_backup\
sudo chmod -R 770 /usr/lucidum_backup
```

## Run update-manager api with gunicorn

```shell
gunicorn api_handler:app -k uvicorn.workers.UvicornH11Worker
```

## API documentation URLs

* Swagger (http://localhost:8000/docs)
* ReDoc (http://localhost:8000/redoc)
