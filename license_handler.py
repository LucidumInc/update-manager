'''
pip install pycrypto pycryptodome pycryptodomex
'''

def reformat_keys(pri_key=None, pub_key=None):
    restore_key = lambda key : ''.join([key[i:min(i+64, len(key))] + '\n' for i in range(0, len(key), 64)])
    if pri_key != None:
        pri_key = "-----BEGIN RSA PRIVATE KEY-----\n" + restore_key(pri_key) + "-----END RSA PRIVATE KEY-----"
    if pub_key != None:
        pub_key = "-----BEGIN PUBLIC KEY-----\n" + restore_key(pub_key) + "-----END PUBLIC KEY-----"
    return pri_key, pub_key

def generate_key_pair():
    from Crypto import Random
    from Crypto.PublicKey import RSA

    # generate private public SSL Key
    random_generator = Random.new().read
    rsa = RSA.generate(2048, random_generator)
    private_pem = rsa.exportKey()
    public_pem = rsa.publickey().exportKey()

    return private_pem.decode('utf8'), public_pem.decode('utf8')


# Generate and return private key, public key, and license
def generate_license(license_data, pri_key=None, pub_key=None):
    import base64
    from M2Crypto import BIO, RSA

    if pri_key == None or pub_key == None:
        pri_key, pub_key = generate_key_pair()

    pri_bio = BIO.MemoryBuffer(pri_key.encode('utf-8'))  # Load private key
    pri_rsa = RSA.load_key_bio(pri_bio)

    origin_content = license_data.encode("utf8")
    content_length = len(origin_content)

    # because content is too large for key size,
    # so we need split to many blocks to encrypt
    keyByteSize = 2048 / 8
    encryptBlockSize = int(keyByteSize - 11)
    nBlock = int(content_length / encryptBlockSize)
    if content_length % encryptBlockSize > 0:
        nBlock = nBlock + 1

    total_license = b''
    total_secret = b''
    offset = 0
    for n in range(nBlock):
        inputLen = content_length - offset
        if inputLen > encryptBlockSize:
            inputLen = encryptBlockSize
        secret = pri_rsa.private_encrypt(origin_content[offset:offset + inputLen], RSA.pkcs1_padding)
        total_secret = total_secret + secret
        offset = int(offset + encryptBlockSize)

    # Reformat license keys
    pri_key = ''.join(pri_key.splitlines()[1:-1])
    pub_key = ''.join(pub_key.splitlines()[1:-1])

    total_license = base64.b64encode(total_secret)  # Ciphertext base64 encoding
    total_license = total_license.decode("utf8") + ":" + pub_key

    return pri_key, pub_key, total_license


def decrypt(license, pub_key):
    import base64
    from M2Crypto import BIO, RSA

    # decrypt
    pub_bio = BIO.MemoryBuffer(pub_key.encode('utf-8'))  # Public key string
    pub_rsa = RSA.load_pub_key_bio(pub_bio)  # Load public key

    cipher = base64.b64decode(license.split(':')[0])
    keyByteSize = 2048 / 8
    decryptBlockSize = keyByteSize - 11
    nBlock = len(cipher) / keyByteSize

    plain = b''
    offset = 0
    while (offset < len(cipher)):
        inputLen = len(cipher) - offset
        if inputLen > keyByteSize:
            inputLen = keyByteSize
        plain = plain + pub_rsa.public_decrypt(cipher[offset:int(offset+inputLen)], RSA.pkcs1_padding)
        offset = int(offset + keyByteSize)
    
    return plain.decode('utf-8')
