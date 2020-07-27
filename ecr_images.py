from dynaconf import settings

HOST_BASE = settings.get('HOST_BASE')
ECR_BASE = settings.get('ECR_BASE')

ecr_images = [
    {
        "name": "connector-aws",
        "version": "latest",
        "hostPath": HOST_BASE + "/connector-aws/external",
        "dockerPath": "/tmp/app/external"
    },
    {   "name": "python/ml",
        "version": "latest",
        "hostPath": HOST_BASE + "/ml_merger/custom_rules",
        "dockerPath": "/home/custom_rules"
    },
    {   "name": "mvp1_backend",
        "version": "latest",
    }
]

def get_ecr_images():
    for ecr_image in ecr_images:
        ecr_image["image"] = "{}/{}:{}".format(ECR_BASE, ecr_image["name"], ecr_image["version"])
    return ecr_images
