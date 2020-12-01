from behave import *
import os


@given('crond is running')
def step_impl(context):
  os.system('systemctl status crond')

@when('crontab directory "{crontab_dir}" exists and is not empty')
def step_impl(context, crontab_dir):
  context.crontab_dir = crontab_dir
  assert os.path.isdir(crontab_dir)
  assert len(os.listdir(crontab_dir)) > 0

@when('crontab file "{crontab_file}" exists')
def step_impl(context, crontab_file):
  assert os.path.isfile(context.crontab_dir + '/' + crontab_file)

@then('ensure cronjobs are installed')
def step_impl(context):
  status_code = os.system('crontab -l | grep getSysInfo.sh > /dev/null')
  assert status_code == 0
