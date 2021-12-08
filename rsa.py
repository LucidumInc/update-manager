import datetime
import os

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, dh
from cryptography.x509.oid import NameOID

KEY_DIR = "keys"
KEY_SIZE = 2048
CA_EXPIRE = 3650
KEY_EXPIRE = 3650
KEY_NAME = "EasyRSA"

SERVER_NETSCAPE_CERT_TYPE = "server"
SERVER_NETSCAPE_COMMENT = "Easy-RSA Generated Server Certificate"
CLIENT_NETSCAPE_COMMENT = "Easy-RSA Generated Certificate"

DEFAULT_NAME_ATTRIBUTES = {
    "COUNTRY_NAME": "US",
    "STATE_OR_PROVINCE_NAME": "CA",
    "LOCALITY_NAME": "SanFrancisco",
    "COMMON_NAME": "lucidum CA",
    "ORGANIZATION_NAME": "lucidum",
    "ORGANIZATIONAL_UNIT_NAME": "saas",
    "EMAIL_ADDRESS": "demo@lucidum.io",
}


class OID:
    NAME = x509.ObjectIdentifier("2.5.4.41")
    NS_CERT_TYPE = x509.ObjectIdentifier("2.16.840.1.113730.1.1")
    NS_COMMENT = x509.ObjectIdentifier("2.16.840.1.113730.1.13")


def build_ca(name: str = "ca", key_dir: str = KEY_DIR, name_attrs: dict = None) -> None:
    if name_attrs is None:
        name_attrs = {}

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    name_attributes = {**DEFAULT_NAME_ATTRIBUTES}
    name_attributes.update(name_attrs)
    x509_name = [
        x509.NameAttribute(OID.NAME, KEY_NAME),
    ]
    for oid_name, value in name_attributes.items():
        oid = getattr(NameOID, oid_name, None)
        if not oid:
            continue
        x509_name.append(x509.NameAttribute(oid, value))
    subject = issuer = x509.Name(x509_name)
    serial_number = x509.random_serial_number()
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(issuer)
    builder = builder.not_valid_before(datetime.datetime.utcnow())
    builder = builder.not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=CA_EXPIRE))
    builder = builder.serial_number(serial_number)
    builder = builder.public_key(public_key)
    builder = builder.add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=False,
    )
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
    )
    aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key)
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier(aki.key_identifier, [x509.DirectoryName(subject)], serial_number), critical=False
    )
    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=default_backend()
    )

    os.makedirs(key_dir, exist_ok=True)
    with open(os.path.join(key_dir, f"{name}.key"), "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with open(os.path.join(key_dir, f"{name}.crt"), "wb") as f:
        f.write(certificate.public_bytes(
            encoding=serialization.Encoding.PEM,
        ))


def build_key_server(
    name: str,
    key_dir: str = KEY_DIR,
    ca_key_filepath: str = None,
    ca_crt_filepath: str = None,
    name_attrs: dict = None,
) -> None:
    if name_attrs is None:
        name_attrs = {}

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    ca_key_path = ca_key_filepath if ca_key_filepath is not None else os.path.join(key_dir, "ca.key")
    with open(ca_key_path, "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

    ca_crt_path = ca_crt_filepath if ca_crt_filepath is not None else os.path.join(key_dir, "ca.crt")
    with open(ca_crt_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read(), backend=default_backend())

    name_attributes = {**DEFAULT_NAME_ATTRIBUTES}
    name_attributes.update(name_attrs)
    name_attributes["COMMON_NAME"] = name
    x509_name = [
        x509.NameAttribute(OID.NAME, KEY_NAME),
    ]
    for oid_name, value in name_attributes.items():
        oid = getattr(NameOID, oid_name, None)
        if not oid:
            continue
        x509_name.append(x509.NameAttribute(oid, value))

    subject_name = x509.Name(x509_name)
    csr_builder = x509.CertificateSigningRequestBuilder()
    csr_builder = csr_builder.subject_name(subject_name)
    csr = csr_builder.sign(private_key, algorithm=hashes.SHA256(), backend=default_backend())

    cert_builder = x509.CertificateBuilder()
    cert_builder = cert_builder.subject_name(subject_name)
    cert_builder = cert_builder.issuer_name(ca_cert.issuer)
    cert_builder = cert_builder.public_key(public_key)
    cert_builder = cert_builder.serial_number(x509.random_serial_number())
    cert_builder = cert_builder.not_valid_before(datetime.datetime.utcnow())
    cert_builder = cert_builder.not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=KEY_EXPIRE))
    cert_builder = cert_builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=False)
    cert_builder = cert_builder.add_extension(
        x509.UnrecognizedExtension(oid=OID.NS_CERT_TYPE, value=SERVER_NETSCAPE_CERT_TYPE.encode()), critical=False
    )
    cert_builder = cert_builder.add_extension(
        x509.UnrecognizedExtension(oid=OID.NS_COMMENT, value=SERVER_NETSCAPE_COMMENT.encode()), critical=False
    )
    cert_builder = cert_builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key())
    cert_builder = cert_builder.add_extension(
        x509.AuthorityKeyIdentifier(aki.key_identifier, [x509.DirectoryName(ca_cert.subject)], ca_cert.serial_number),
        critical=False
    )
    cert_builder = cert_builder.add_extension(x509.ExtendedKeyUsage([x509.OID_SERVER_AUTH]), critical=False)
    cert_builder = cert_builder.add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False
        ),
        critical=False
    )
    cert_builder = cert_builder.add_extension(
        x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False
    )
    cert = cert_builder.sign(ca_key, algorithm=hashes.SHA256(), backend=default_backend())

    os.makedirs(key_dir, exist_ok=True)
    with open(os.path.join(key_dir, f"{name}.key"), "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with open(os.path.join(key_dir, f"{name}.crt"), "wb") as f:
        f.write(cert.public_bytes(encoding=serialization.Encoding.PEM))

    with open(os.path.join(key_dir, f"{name}.csr"), "wb") as f:
        f.write(csr.public_bytes(encoding=serialization.Encoding.PEM))


def build_key(
    name: str,
    key_dir: str = KEY_DIR,
    ca_key_filepath: str = None,
    ca_crt_filepath: str = None,
    name_attrs: dict = None,
) -> None:
    if name_attrs is None:
        name_attrs = {}

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    ca_key_path = ca_key_filepath if ca_key_filepath is not None else os.path.join(key_dir, "ca.key")
    with open(ca_key_path, "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

    ca_crt_path = ca_crt_filepath if ca_crt_filepath is not None else os.path.join(key_dir, "ca.crt")
    with open(ca_crt_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read(), backend=default_backend())

    name_attributes = {**DEFAULT_NAME_ATTRIBUTES}
    name_attributes.update(name_attrs)
    name_attributes["COMMON_NAME"] = name
    x509_name = [
        x509.NameAttribute(OID.NAME, KEY_NAME),
    ]
    for oid_name, value in name_attributes.items():
        oid = getattr(NameOID, oid_name, None)
        if not oid:
            continue
        x509_name.append(x509.NameAttribute(oid, value))

    subject_name = x509.Name(x509_name)
    csr_builder = x509.CertificateSigningRequestBuilder()
    csr_builder = csr_builder.subject_name(subject_name)
    csr = csr_builder.sign(private_key, algorithm=hashes.SHA256(), backend=default_backend())

    cert_builder = x509.CertificateBuilder()
    cert_builder = cert_builder.subject_name(subject_name)
    cert_builder = cert_builder.issuer_name(ca_cert.issuer)
    cert_builder = cert_builder.public_key(public_key)
    cert_builder = cert_builder.serial_number(x509.random_serial_number())
    cert_builder = cert_builder.not_valid_before(datetime.datetime.utcnow())
    cert_builder = cert_builder.not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=KEY_EXPIRE))
    cert_builder = cert_builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=False)
    cert_builder = cert_builder.add_extension(
        x509.UnrecognizedExtension(oid=OID.NS_COMMENT, value=CLIENT_NETSCAPE_COMMENT.encode()), critical=False
    )
    cert_builder = cert_builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key())
    cert_builder = cert_builder.add_extension(
        x509.AuthorityKeyIdentifier(aki.key_identifier, [x509.DirectoryName(ca_cert.subject)], ca_cert.serial_number),
        critical=False
    )
    cert_builder = cert_builder.add_extension(x509.ExtendedKeyUsage([x509.OID_CLIENT_AUTH]), critical=False)
    cert_builder = cert_builder.add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False
        ),
        critical=False
    )
    cert_builder = cert_builder.add_extension(
        x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False
    )
    cert = cert_builder.sign(ca_key, algorithm=hashes.SHA256(), backend=default_backend())

    os.makedirs(key_dir, exist_ok=True)
    with open(os.path.join(key_dir, f"{name}.key"), "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with open(os.path.join(key_dir, f"{name}.crt"), "wb") as f:
        f.write(cert.public_bytes(encoding=serialization.Encoding.PEM))

    with open(os.path.join(key_dir, f"{name}.csr"), "wb") as f:
        f.write(csr.public_bytes(encoding=serialization.Encoding.PEM))


def build_dh(key_dir: str = KEY_DIR) -> None:
    parameters = dh.generate_parameters(generator=2, key_size=KEY_SIZE, backend=default_backend())
    os.makedirs(key_dir, exist_ok=True)
    with open(os.path.join(key_dir, f"dh{KEY_SIZE}.pem"), "wb") as f:
        f.write(parameters.parameter_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.ParameterFormat.PKCS3
        ))
