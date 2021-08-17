from behave import *
import glob
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
  for filepath in glob.iglob(context.install_path + '/**/**', recursive=True):
    if not os.path.islink(filepath):
      file_uid = os.stat(filepath).st_uid
      user_uid = pwd.getpwnam(user).pw_uid
      assert file_uid != user_uid

@then('ensure files and directories do not have world writable "{bit1}" "{bit2}" "{bit3}" "{bit4}" bits')
def step_impl(context, bit1, bit2, bit3, bit4):
  for filepath in glob.iglob(context.install_path + '/**/**', recursive=True):
    if not os.path.islink(filepath):
      status = os.stat(filepath)
      assert int(oct(status.st_mode)[-1:]) != int(bit1)
      assert int(oct(status.st_mode)[-1:]) != int(bit2)
      assert int(oct(status.st_mode)[-1:]) != int(bit3)
      assert int(oct(status.st_mode)[-1:]) != int(bit4)
