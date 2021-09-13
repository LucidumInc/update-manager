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
