import click
import json
from loguru import logger

from config_handler import get_images_from_ecr, get_local_images, get_images, get_key_dir_config
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
#@history_command(command="ecr", get_history_entries=get_install_ecr_entries, get_images=get_images_from_ecr)
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
    from handlers.mongo_import import run
    run('postReport.json', 'biQuery_lucidum_report', drop=True)
    run('postDashboard.json', 'biQuery_lucidum_dashboard', drop=True)
    run('postDynamicFieldDef.json', 'local_dynamic_field_definition', override=True, upsert_fields='field_name')
    run('postDynamicFieldDisplay.json', 'field_display_local', override=True, upsert_fields='field_name')
    run('postSavedQuery.json', 'Query_Builder', override=True, upsert_fields='name')

@cli.command()
def update_action_config():
    """
    Update Action Config in mongo.
    Place json files under /usr/lucidum/mongo/db folder
    """
    from handlers.mongo_import import run
    run('emailActionConfig.json', 'local_integration_configuration', override=True, upsert_fields='config_name')
    

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
    from api_handler import get_local_connectors
    from docker_service import run_docker_container
    connectors = get_local_connectors()    
    for connector in connectors:
        try:
            image = f"connector-{connector['type']}:{connector['version']}"
            command = f'bash -c "python lucidum_{connector["type"]}.py config-to-db"'
            out = run_docker_container(
                image, stdout=True, stderr=True, remove=True, network="lucidum_default", command=command
            )
            logger.info(connector)
            logger.info(out.decode())
        except Exception as e:
            logger.warning(f"config-to-db error: {e}")

@cli.command()
def df_to_sl():
    from config_handler import get_mongo_config
    from urllib.parse import quote_plus
    from pymongo import MongoClient
    from datetime import datetime
    uri_pattern = "mongodb://{user}:{password}@{host}:{port}/?authSource={db}"
    configs = get_mongo_config()
    mongo_db = MongoClient(uri_pattern.format(
                           user=quote_plus(configs["mongo_user"]), password=quote_plus(configs["mongo_pwd"]),
                           host=configs["mongo_host"], port=configs["mongo_port"], db=configs["mongo_db"]))
    dynamic_field_coll = mongo_db[configs["mongo_db"]]['local_dynamic_field_definition']
    dynamic_field_done_coll = mongo_db[configs["mongo_db"]]['local_dynamic_field_definition_done']
    smart_label_coll = mongo_db[configs["mongo_db"]]['smart_label']
    field_display_coll = mongo_db[configs["mongo_db"]]['field_display_local']
    df_records = dynamic_field_coll.find({"field_rule_type": {"$exists": False}})

    def _df_to_smart_label(df_record):
        logger.info(f"***** converting dynamic field: {df_record['field_name']} to smart label")
        filter = ""
        if df_record['field_query_template']:
            if '"filter":' in df_record['field_query_template']:
                filter_obj = json.loads(df_record['field_query_template'])[0]['filter']
                filter = f"[{json.dumps(filter_obj)}]"
            else:
                filter = df_record['field_query_template']
        else:
            logger.warning("cannot convert dynamic field: {df_record['field_name']} it does not have query filter")
            return
        if 'history' in df_record['field_collection'].lower():
            logger.warning("cannot convert dynamic field: {df_record['field_name']} for history tables")
            return
        if df_record['field_type'] == 'Number':
            df_record['field_type'] = 'Integer'
        # delete existing and create smart label record
        smart_label_coll.delete_many({"field_name": df_record['field_name']})
        smart_label_record = {'field_collection': df_record['field_collection'],
                              'field_name': df_record['field_name'],
                              'friendly_name': df_record['field_name'], 'field_description': '*** dynamic field moved to smart label',
                              'field_type': df_record['field_type'],
                              'field_default_value': df_record['field_rule']['not_in_result'],
                              'field_rules': [{'rule_name': 'first_rule',
                                               'field_query_template': filter,
                                               'exists_in_result': df_record['field_rule']['exists_in_result']}],
                              'status': 'COMPLETED',
                              'field_group': 'dynamic', 'created_by': 'admin', 'last_modified_by': 'admin',
                              'created_at': datetime.now(), 'last_modified_at': datetime.now(), '_class': 'com.hicheer.cmdb.domain.SmartLabelEntity'}
        smart_label_coll.insert_one(smart_label_record)
        # delete existing and create field display records
        field_display_coll.delete_many({"field_name": df_record['field_name']})
        _source_mapping = {"AWS_CMDB_Output": ['AWS_CMDB_Output', 'customer_field_Asset_Name'], "User_Combine": ["User_Combine", "customer_field_Owner_Name"]}
        field_position_mapping = {"AWS_CMDB_Output": "asset", "User_Combine": "user"}
        data_type_mapping = {"str": "String","integer": "Integer","boolean": "Binary","float": "Float","list": "List","number": "Float","time": "Time"}
        fd_record = {'field_name': df_record['field_name'], 'field_source': 'DYNAMIC', 'field_description': df_record['field_name'], 'friendly_name': df_record['field_name'],
                     'data_type': data_type_mapping[df_record['field_type'].lower()], 'group': 'Dynamic Fields', 'show_in_result': True, 'show_in_search': True, 'graph': 'none', 'role_of_access': [],
                     'ui_module_settings': [], 'item_fields': [], 'value_2_label': '{}', 'value_example': [], 'priority': 0, 'formatter': '{}', 'formatter_case': '{}',
                     'page_of_display': [], 'module_supported': ['All'], 'field_category': 'dynamic_field',
                     'field_position': field_position_mapping[df_record['field_collection']], '_source': _source_mapping[df_record['field_collection']]}
        field_display_coll.insert_one(fd_record)
        # delete existing and move dynamic field to dynamic field done table
        dynamic_field_coll.delete_many({"field_name": df_record['field_name']})
        dynamic_field_done_coll.insert_one(df_record)

    for df_record in df_records:
        _df_to_smart_label(df_record)


if __name__ == '__main__':
    cli()
