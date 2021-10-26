from behave import *
import pwd
import os


@given('we have a database and web user with user_id "{user_uid}"')
def step_impl(context, user_uid):
  print(user_uid)
  context.user_uid = user_uid
  assert int(user_uid) > 0


@then('ensure database and web user exists')
def step_impl(context):
  print(context.user_uid)
  print(pwd.getpwuid(int(context.user_uid)))
  assert pwd.getpwuid(int(context.user_uid))
  

@given('we have a mongo installation at "{mongo_dir}"')
def step_impl(context, mongo_dir):
  print(mongo_dir)
  assert os.path.exists(mongo_dir)
  
  
@given('mongo_data_dir exists at "{mongo_data_dir}"')
def step_impl(context, mongo_data_dir):
  print(mongo_data_dir)
  context.mongo_data_dir = mongo_data_dir
  assert os.path.exists(mongo_data_dir)


@then('ensure mongo_data_dir is owned by user_id "{user_uid}"')
def step_impl(context, user_uid):
  print(context.mongo_data_dir)
  print(user_uid)
  assert os.stat(context.mongo_data_dir).st_uid == int(user_uid)


@given('we have a mysql installation at "{mysql_dir}"')
def step_impl(context, mysql_dir):
  print(mysql_dir)
  context.mysql_dir = mysql_dir
  assert os.path.exists(mysql_dir)


@given('mysql_data_dir exists at "{mysql_data_dir}"')
def step_impl(context, mysql_data_dir):
  print(mysql_data_dir)
  context.mysql_data_dir = mysql_data_dir
  assert os.path.exists(mysql_data_dir)


@given('mysql_config exists at "{mysql_config}"')
def step_impl(context, mysql_config):
  print(mysql_config)
  context.mysql_config = mysql_config
  assert os.path.exists(mysql_config)


@then('ensure mysql_data_dir is owned by user_id "{user_uid}"')
def step_impl(context, user_uid):
  print(context.mysql_data_dir)
  print(user_uid)
  assert os.stat(context.mysql_data_dir).st_uid == int(user_uid)


@then('ensure mysql_config is owned by user_id "{user_uid}"')
def step_impl(context, user_uid):
  print(context.mysql_config)
  print(user_uid)
  assert os.stat(context.mysql_config).st_uid == int(user_uid)


@given('we have a web installation at "{web_dir}"')
def step_impl(context, web_dir):
  print(web_dir)
  context.web_dir = web_dir
  assert os.path.exists(web_dir)

@then('ensure web_dir is owned by user_id "{user_uid}"')
def step_impl(context, user_uid):
  print(context.web_dir)
  print(user_uid)
  assert os.stat(context.web_dir).st_uid == int(user_uid)
