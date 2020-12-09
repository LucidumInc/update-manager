from behave import *
import pwd
import os

@given('we have a lucidum installation')
def step_impl(context):
  pass

@when('lucidum directory is "{install_path}"')
def step_impl(context, install_path):
  context.install_path = install_path
  assert os.path.isdir(install_path)

@then('ensure files and directories do not have "{user}" ownership')
def step_impl(context, user):
  for path in os.listdir(context.install_path):
    assert pwd.getpwuid(os.stat(context.install_path + '/' + path).st_uid) != user
