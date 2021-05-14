from urllib.parse import urlparse

import boto3
import shutil


def is_s3_url(url):
    if not isinstance(url, str):
        return False
    return urlparse(url).scheme in ["s3", "s3n", "s3a"]


class LocalFileHandler:

    def write(self, path: str, data):
        with open(path, "wb+") as f:
            f.write(data)

    def copy_file(self, src: str, dst: str):
        shutil.copyfile(src, dst)

    def place_file(self, src: str, dst: str):
        shutil.copyfile(src, dst)


class S3FileHandler:

    def __init__(self) -> None:
        self._s3_resource = None

    @property
    def s3_resource(self):
        if self._s3_resource is None:
            self._s3_resource = boto3.resource("s3")
        return self._s3_resource

    def _parse_url(self, url: str):
        parsed = urlparse(url, allow_fragments=False)
        key = f"{parsed.path.lstrip('/')}?{parsed.query}" if parsed.query else parsed.path.lstrip("/")
        return parsed.netloc, key

    def write(self, path: str, data):
        bucket_name, key = self._parse_url(path)
        obj = self.s3_resource.Object(bucket_name, key)
        obj.put(Body=data)

    def copy_file(self, src: str, dst: str):
        bucket_name, key = self._parse_url(dst)
        obj = self.s3_resource.Object(bucket_name, key)
        obj.upload_file(src)

    def place_file(self, src: str, dst: str):
        bucket_name, key = self._parse_url(src)
        obj = self.s3_resource.Object(bucket_name, key)
        obj.download_file(dst)


def get_file_handler(path: str):
    if is_s3_url(path):
        file_handler = S3FileHandler()
    else:
        file_handler = LocalFileHandler()

    return file_handler
