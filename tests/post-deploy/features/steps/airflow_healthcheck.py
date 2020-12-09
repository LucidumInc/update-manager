from behave import *
import requests
import os


@given('we have "{airflow_webserver}" running')
def step_impl(context, airflow_webserver):
  status_code = os.system('systemctl status ' + airflow_webserver + '>/dev/null')
  assert status_code == 0

@when('airflow healthcheck "{healthcheck_endpoint}" is available')
def step_impl(context, healthcheck_endpoint):
  try:
    context.http_status = requests.get(healthcheck_endpoint).status_code
  except:
    context.failed = True

@then('ensure healthcheck returns "{expected_status_code}" http status code')
def step_impl(context, expected_status_code):
  assert str(context.http_status) == expected_status_code

@given('we have "{airflow_dag_name}" dag configured')
def step_impl(context, airflow_dag_name):
  context.status_codes = []
  context.status_codes.append(os.system('/usr/lucidum/venv/bin/airflow list_tasks ' + \
                                        airflow_dag_name + '>/dev/null'))

@then('ensure dags are enabled')
def step_impl(context):
  for code in context.status_codes:
    if code != 0:
      context.failed = True
