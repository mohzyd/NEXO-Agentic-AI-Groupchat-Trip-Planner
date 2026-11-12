from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.exceptions import InvalidTag
from config import (
    APP_CRYPTO_SALT_SIZE,
    APP_CRYPTO_NONCE_SIZE,
    APP_CRYPTO_KEY_SIZE,
    APP_CRYPTO_SCRYPT_N,
    APP_CRYPTO_SCRYPT_R,
    APP_CRYPTO_SCRYPT_P,
    APP_CRYPTO_HEADER,
    APP_CRYPTO_ENCRYPTION_KEY
)
import os, base64

class Encryptor:
    @staticmethod
    def encrypt(plaintext: str, key: str = APP_CRYPTO_ENCRYPTION_KEY) -> str:
        """
        Encrypts a plaintext string using AES-GCM with a derived key from the provided key.
        
        Args:
            plaintext (str): The plaintext string to encrypt.
            key (str): The key to derive the encryption key from.
        
        Returns:
            str: The base64-encoded encrypted data.
        """

        if not isinstance(plaintext, str) or len(plaintext.strip()) == 0:
            raise ValueError("[Encryption : Encrypt] Plaintext must be a non-empty string")
        
        salt        = os.urandom(APP_CRYPTO_SALT_SIZE)
        derived_key = Encryptor.__derive_key(salt, key)
        nonce       = os.urandom(APP_CRYPTO_NONCE_SIZE)
        cipher      = AESGCM(derived_key)
        text        = cipher.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload     = APP_CRYPTO_HEADER + salt + nonce + text
        return base64.urlsafe_b64encode(payload).decode("ascii")

    @staticmethod
    def decrypt(ciphertext: str, key: str = APP_CRYPTO_ENCRYPTION_KEY) -> str:
        """
        Decrypts a base64-encoded encrypted data string using AES-GCM with a derived key from the provided key.
        
        Args:
            ciphertext (str): The base64-encoded encrypted data string.
            key (str): The key to derive the encryption key from.
        
        Returns:
            str: The decrypted plaintext string.
        """

        if not isinstance(ciphertext, str) or len(ciphertext.strip()) == 0:
            raise ValueError("[Encryption : Decrypt] Encrypted data must be a non-empty string")
        
        try:
            payload  = base64.b64decode(ciphertext.encode("ascii"), altchars=b"-_", validate=True)
            min_size = len(APP_CRYPTO_HEADER) + APP_CRYPTO_SALT_SIZE + APP_CRYPTO_NONCE_SIZE + 16
            
            if len(payload) < min_size:
                raise Exception()

            offset = len(APP_CRYPTO_HEADER)
            if payload[ : offset] != APP_CRYPTO_HEADER:
                raise Exception()

            salt    = payload[offset : offset + APP_CRYPTO_SALT_SIZE]
            offset += APP_CRYPTO_SALT_SIZE
            
            nonce   = payload[offset : offset + APP_CRYPTO_NONCE_SIZE]
            offset += APP_CRYPTO_NONCE_SIZE
            
            encrypted_data = payload[offset : ]
            derived_key    = Encryptor.__derive_key(salt, key)
            cipher         = AESGCM(derived_key)
            text           = cipher.decrypt(nonce, encrypted_data, None)
            return text.decode("utf-8")
        except (InvalidTag, Exception):
            raise ValueError("[Encryption : Decrypt] Invalid encrypted data")

    @staticmethod
    def __derive_key(salt: bytes, key: str = APP_CRYPTO_ENCRYPTION_KEY) -> bytes:
        """
        Derives a key from the provided key using Scrypt.
        
        Args:
            salt (bytes): The salt to use for key derivation.
            key (str): The key to derive the encryption key from.
        
        Returns:
            bytes: The derived key in bytes.
        """
        if not isinstance(key, str) or len(key.strip()) == 0:
            raise ValueError("[Encryption : KEY] Encryption key must be a non-empty string")

        kdf = Scrypt(
            salt=salt,
            length=APP_CRYPTO_KEY_SIZE,
            n=APP_CRYPTO_SCRYPT_N,
            r=APP_CRYPTO_SCRYPT_R,
            p=APP_CRYPTO_SCRYPT_P
        )

        return kdf.derive(key.encode("utf-8"))
