import os
import tarfile
import click
from docker import DockerClient
from loguru import logger

client = DockerClient.from_env()
ecr_images = [
    {
        "name": "connector-aws",
        "rename": "connector-aws:latest",
        "image": "308025194586.dkr.ecr.us-west-1.amazonaws.com/connector-aws:latest",
        "hostPath": "/home/demo/lucidum/connector-aws/external",
        "dockerPath": "/tmp/app/external"
    },
    {   "name": "ml_merger",
        "rename": "ml_merger:latest",
        "image": "308025194586.dkr.ecr.us-west-1.amazonaws.com/python/ml:latest",
        "hostPath": "/home/demo/lucidum/ml_merger/custom_rules",
        "dockerPath": "/home/custom_rules"
    }
]

def _remove_image(docker_client, image_name):
    result = docker_client.images.list(image_name)
    if len(result) > 0:
        docker_client.images.remove(image_name)

@click.group()
def cli():
    pass

@cli.command()
@click.option('--copy_default', '-c', default=False, help='copy default files from docker to host')
@click.option('--rename', '-r',  default=False, help='rename image name')
def update(copy_default, rename):
    logger.info(f"copy_default: {copy_default}, rename: {rename}")
    for ecr_image in ecr_images:
        _remove_image(client, ecr_image['image'])
        _remove_image(client, ecr_image['rename'])
        image = client.images.pull(ecr_image['image'])
        logger.info(f"updated to latest image, id: {image.short_id} tag: {image.tags}")
        if rename:
            image.tag(ecr_image['rename'])
            client.images.remove(ecr_image['image'])
        if copy_default:
            logger.info(f"copy default files from {image.tags} docker f{ecr_image['dockerPath']} to host f{ecr_image['hostPath']}")
            container = client.containers.create(image, 'bash')
            bits, stat = container.get_archive(ecr_image['dockerPath'] + '/.')
            with open(ecr_image['hostPath'] + '/docker.tar', 'wb') as f:
                for chunk in bits:
                    f.write(chunk)
            tar = tarfile.open(ecr_image["hostPath"] + "/docker.tar")
            tar.extractall(path=ecr_image["hostPath"] + "/")
            tar.close()
            logger.info("clean up")
            container.remove()
            os.remove(ecr_image["hostPath"] + "/docker.tar")

if __name__ == '__main__':
    cli()
