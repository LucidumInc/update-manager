from behave import *
import pwd
import os


@given('we have a database user with user_id "{db_uid}"')
def step_impl(context, db_uid):
  print(db_uid)
  context.db_uid = db_uid
  assert int(db_uid) > 0


@then('ensure database user exists')
def step_impl(context):
  print(context.db_uid)
  print(pwd.getpwuid(context.db_uid)
  assert pwd.getpwuid(context.db_uid)
  

@given('we have a mongo installation at "{mongo_dir}"')
def step_impl(context, mongo_dir):
  print(mongo_dir)
  assert os.path.exists(mongo_dir)
  
  
@given('mongo_data_dir exists at "{mongo_data_dir}"')
def step_impl(context, mongo_data_dir):
  print(mongo_data_dir)
  context.mongo_data_dir = mongo_data_dir
  assert os.path.exists(mongo_data_dir)


@then('ensure mongo_data_dir is owned by database user'):
def step_impl(context):
  print(context.mongo_data_dir)
  print(context.db_uid)
  assert os.stat(context.mongo_data_dir).st_uid == int(context.db_uid)


@given('we have a mysql installation at "{mysql_dir}"')
def step_impl(context, mysql_dir):
  print(mysql_dir)
  context.mysql_dir = mysql_dir
  assert os.path.exists(mysql_dir)


@given('mysql_data_dir is present at "{mysql_data_dir}"')
def step_impl(context, mysql_data_dir):
  print(mysql_data_dir)
  context.mysql_data_dir = mysql_data_dir
  assert os.path.exists(mysql_data_dir)


@given('mysql_config is present at "{mysql_config}"')
def step_impl(context, mysql_config):
  print(mysql_config)
  context.mysql_config = mysql_config
  assert os.path.exists(mysql_config)


@then('ensure mysql_data_dir is owned by database user')
def step_impl(context):
  print(context.mysql_data_dir)
  print(context.db_uid)
  assert os.stat(context.mysql_data_dir).st_uid == int(context.db_uid)


@then('ensure mysql_config is owned by database user')
def step_impl(context):
  print(context.mysql_config)
  print(context.db_uid)
  assert os.stat(context.mysql_config).st_uid == int(context.db_uid)
