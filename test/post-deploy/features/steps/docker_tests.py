from behave import *
import docker

client = docker.from_env()


@given('docker image "{docker_image}" is local')
def step_impl(context, docker_image):
  for image in client.images.list():
    if docker_image in str(image):
      break
  else:
    assert context.failed is True


@then('docker containers should be running')
def step_impl(context):
  num_containers = len(client.containers.list(all=True))

  # NOTE: parse docker-compose.yml and test each container is running
  #       rather than just testing number of containers
  if num_containers < 4:
    assert context.failed is True
