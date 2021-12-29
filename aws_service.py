import base64
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3


class ECRClient:

    def __init__(self, region, access_key=None, secret_key=None) -> None:
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._client = None
        self._auth_config = None

    @property
    def client(self):
        if self._client is None:
            self._client = self._get_ecr_client()
        return self._client

    @property
    def auth_config(self):
        if self._auth_config is None:
            self._auth_config = self._get_auth_config()
        else:
            if datetime.now(timezone.utc) > self._auth_config["expiresAt"]:
                self._auth_config = self._get_auth_config()
        return self._auth_config

    def get_repositories(self):
        return self._paginate(lambda r: r["repositories"], self.client.describe_repositories)

    def get_images(self, repository_name):
        return self._paginate(
            lambda r: r["imageDetails"], self.client.describe_images, repositoryName=repository_name
        )

    def _get_auth_config(self):
        response = self.client.get_authorization_token()
        authorization_data = response["authorizationData"][0]
        credentials = base64.b64decode(authorization_data.pop("authorizationToken")).decode().split(":")
        authorization_data["username"] = credentials[0]
        authorization_data["password"] = credentials[1]
        authorization_data["registry"] = urlparse(authorization_data["proxyEndpoint"]).hostname
        return authorization_data

    def _get_ecr_client(self):
        kwargs = {
            "region_name": self._region,
            "verify": False
        }
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key
        return boto3.client("ecr", **kwargs)

    @staticmethod
    def _paginate(extract_response_data, func, **kwargs):
        data = []
        response = func(**kwargs)
        data += extract_response_data(response)
        while "nextToken" in response:
            response = func(nextToken=response["nextToken"], **kwargs)
            data += extract_response_data(response)
        return data
