#!/usr/bin/env python3
"""
Decrypt /challenge/.config/.level_metadata file
This file is encrypted with Fernet using a password-derived key
"""

import sys
import base64
import hashlib
import json
from cryptography.fernet import Fernet

# Password used for encryption
FERNET_PASSWORD = "why four out tho"

def derive_key_from_password(password):
    """
    Derive Fernet key from password using SHA-256
    Returns base64-urlsafe encoded key (32 bytes)
    """
    # Create SHA-256 hash of password
    hash_obj = hashlib.sha256()
    hash_obj.update(password.encode('utf-8'))
    key_bytes = hash_obj.digest()
    
    # Convert to base64-urlsafe encoding (Fernet requirement)
    key_b64 = base64.urlsafe_b64encode(key_bytes)
    
    return key_b64

def decrypt_fernet(encrypted_base64, key):
    """
    Decrypt base64-encoded Fernet encrypted data
    """
    # Decode from base64 to get the actual encrypted token
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Create Fernet cipher with the key
    fernet = Fernet(key)
    
    # Decrypt
    decrypted_bytes = fernet.decrypt(encrypted_data)
    decrypted = decrypted_bytes.decode('utf-8')
    
    # Check if result is still base64 encoded (double layer)
    try:
        # Try to decode as base64
        if all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r\t ' for c in decrypted):
            decoded = base64.b64decode(decrypted.strip())
            # Check if it's valid UTF-8
            test = decoded.decode('utf-8')
            decrypted = test
    except:
        # Not double-encoded, use as-is
        pass
    
    return decrypted

def main():
    if len(sys.argv) > 1:
        metadata_path = sys.argv[1]
    else:
        metadata_path = '/challenge/.config/.level_metadata'
    
    try:
        # Read the encrypted file
        with open(metadata_path, 'r') as f:
            encrypted_content = f.read().strip()
        
        # Derive key from password
        key = derive_key_from_password(FERNET_PASSWORD)
        
        # Decrypt the content
        decrypted_json = decrypt_fernet(encrypted_content, key)
        
        # Parse and pretty-print JSON
        data = json.loads(decrypted_json)
        print(json.dumps(data, indent=2))
        
        return 0
        
    except FileNotFoundError:
        print(f"Error: File not found: {metadata_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON after decryption: {e}", file=sys.stderr)
        print(f"Decrypted content preview: {decrypted_json[:200]}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
