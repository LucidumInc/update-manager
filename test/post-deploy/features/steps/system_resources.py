from behave import *
import psutil



@given('we have a running lucidum system')
def step_impl(context):
  pass


@when('lucidum minimum memory is "{min_mem}" bytes')
def step_impl(context, min_mem):
  context.min_mem = min_mem
  assert int(min_mem) > 0

@when('lucidum minimum cpu is "{min_cpu}" cores')
def step_impl(context, min_cpu):
  context.min_cpu = min_cpu
  assert int(min_cpu) > 0

@when('lucidum minimum disk is "{min_disk}" bytes')
def step_impl(context, min_disk):
  context.min_disk = min_disk
  assert int(min_disk) > 0


@then('ensure system memory is sufficient')
def step_impl(context):
  print(context.min_mem)
  print(psutil.virtual_memory().total)
  assert int(psutil.virtual_memory().total) >= int(context.min_mem)

@then('ensure system cpu is sufficient')
def step_impl(context):
  print(context.min_cpu)
  print(psutil.cpu_count())
  assert int(psutil.cpu_count()) >= int(context.min_cpu)

@then('ensure system disk is sufficient')
def step_impl(context):
  print(context.min_disk)
  print(psutil.disk_usage('/').total)
  assert int(psutil.disk_usage('/').total) >= int(context.min_disk)
