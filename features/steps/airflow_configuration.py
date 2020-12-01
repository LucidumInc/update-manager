from behave import *
import os

@given('we have airflow installed')
def step_impl(context):
  pass

@when('the configured home directory is "{airflow_home}"')
def step_impl(context, airflow_home):
  context.airflow_home = airflow_home
  assert os.path.isdir(airflow_home)

@then('ensure "{airflow_configuration}" is correct')
def step_impl(context, airflow_configuration):
  dags_cfg = 'dags_folder = ' + context.airflow_home + '/dags'
  plugin_cfg = 'plugins_folder = ' + context.airflow_home + '/plugins'
  child_logs_cfg = 'child_process_log_directory = ' + context.airflow_home + '/logs/scheduler'
  with open(context.airflow_home + '/' + airflow_configuration, 'r+') as cfg:

    for line in cfg:
      if dags_cfg in line:
        break
    else:
      assert context.failed is True

    for line in cfg:
      if plugin_cfg in line:
        break
    else:
      assert context.failed is True

    for line in cfg:
      if child_logs_cfg in line:
        break
    else:
      assert context.failed is True
