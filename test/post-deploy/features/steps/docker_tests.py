from behave import *
import docker
import yaml
import os

client = docker.from_env()


@given('docker-compose config "{docker_compose_config}" is present')
def step_impl(context, docker_compose_config):
  context.docker_containers = []

  if os.path.isfile(docker_compose_config):
    with open(docker_compose_config, 'r') as yfile:
      dconf = yaml.safe_load(yfile)
    for key, value in dconf['services'].items():
      context.docker_containers.append(value['image'])

  else:
    assert context.failed is True


@then('docker-compose images should be local')
def step_impl(context):
  docker_images = []

  for local_image in client.images.list():
    # Updated airflow images use an environment variable so strip that off.
    if "AIRFLOW_IMAGE_NAME" in local_image.tags[0]:
      image_name = local_image.tags[0].split(":-", 1)[1].rstrip("}")
      docker_images.append(image_name)
    else:
      docker_images.append(local_image.tags[0])

  for compose_container in context.docker_containers:
    # Updated airflow images use an environment variable so strip that off.
    if "AIRFLOW_IMAGE_NAME" in compose_container:
      compose_container = compose_container.split(":-", 1)[1].rstrip("}")

    if compose_container not in docker_images:
      assert context.failed is True


@then('docker-compose containers should be running')
def step_impl(context):
  local_containers = []

  for container in client.containers.list():
    # Updated airflow images use an environment variable so strip that off.
    if "AIRFLOW_IMAGE_NAME" in container.image.tags[0]:
      image_name = container.image.tags[0].split(":-", 1)[1].rstrip("}")
      local_containers.append(image_name)
    else:
      local_containers.append(container.image.tags[0])

  for compose_container  in context.docker_containers:
    # Updated airflow images use an environment variable so strip that off.
    if "AIRFLOW_IMAGE_NAME" in compose_container:
      compose_container = compose_container.split(":-", 1)[1].rstrip("}")

    if compose_container not in local_containers:
      assert context.failed is True
