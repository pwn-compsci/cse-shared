#!/usr/bin/env node

/**
 * Test utility for Fernet encryption/decryption
 * This script helps test the prompt injection functionality
 */

const crypto = require('crypto');
const fernet = require('fernet');
const fs = require('fs');

const FERNET_PASSWORD = "why four out tho";

/**
 * Derive Fernet key from password using SHA-256
 */
function deriveKeyFromPassword(password) {
    const hash = crypto.createHash('sha256');
    hash.update(password);
    const keyBytes = hash.digest();
    
    // Convert to base64-urlsafe encoding
    const base64 = keyBytes.toString('base64');
    const urlsafe = base64.replace(/\+/g, '-').replace(/\//g, '_');
    
    return urlsafe;
}

/**
 * Encrypt data with Fernet
 */
function encryptFernet(plaintext, key) {
    const secret = new fernet.Secret(key);
    const token = new fernet.Token({ secret: secret });
    return token.encode(plaintext);
}

/**
 * Decrypt Fernet encrypted data
 */
function decryptFernet(encryptedData, key) {
    const secret = new fernet.Secret(key);
    const token = new fernet.Token({
        secret: secret,
        token: encryptedData,
        ttl: 0
    });
    return token.decode();
}

// Example usage
if (require.main === module) {
    console.log('Fernet Encryption/Decryption Test Utility');
    console.log('==========================================\n');
    
    // Sample data
    const sampleData = {
        "prompt_injections": {
            "intro:challenge01": {
                "module": "intro",
                "challenge": "challenge01",
                "prompt": "This is a test prompt that should be injected into copied text.",
                "search_for": "test phrase",
                "behavior_check": true,
                "behavior_description": "Test behavior pattern"
            },
            "basics:challenge02": {
                "module": "basics",
                "challenge": "challenge02",
                "prompt": "Another prompt for testing purposes with multiple lines.\nThis is line 2 of the prompt.",
                "search_for": "another test",
                "behavior_check": false,
                "behavior_description": null
            }
        }
    };
    
    console.log('Sample Data:');
    console.log(JSON.stringify(sampleData, null, 2));
    console.log('\n');
    
    // Step 1: Derive key
    console.log('Step 1: Deriving key from password...');
    const key = deriveKeyFromPassword(FERNET_PASSWORD);
    console.log(`Key: ${key.substring(0, 20)}...`);
    console.log('\n');
    
    // Step 2: Encrypt
    console.log('Step 2: Encrypting data...');
    const plaintext = JSON.stringify(sampleData);
    const encrypted = encryptFernet(plaintext, key);
    console.log(`Encrypted: ${encrypted.substring(0, 50)}...`);
    console.log('\n');
    
    // Step 3: Base64 encode (double layer)
    console.log('Step 3: Base64 encoding...');
    const base64Encoded = Buffer.from(encrypted, 'utf8').toString('base64');
    console.log(`Base64: ${base64Encoded.substring(0, 50)}...`);
    console.log('\n');
    
    // Step 4: Decrypt (reverse process)
    console.log('Step 4: Decrypting...');
    const decrypted = decryptFernet(encrypted, key);
    const decryptedData = JSON.parse(decrypted);
    console.log('Decrypted data:');
    console.log(JSON.stringify(decryptedData, null, 2));
    console.log('\n');
    
    // Step 5: Test double base64 layer
    console.log('Step 5: Testing double base64 layer...');
    const decodedBase64 = Buffer.from(base64Encoded, 'base64').toString('utf8');
    const finalDecrypted = decryptFernet(decodedBase64, key);
    const finalData = JSON.parse(finalDecrypted);
    console.log('Final decrypted data:');
    console.log(JSON.stringify(finalData, null, 2));
    console.log('\n');
    
    // Save to file (for testing)
    console.log('Step 6: Saving to test file...');
    const testFilePath = '/tmp/.level_metadata_test';
    fs.writeFileSync(testFilePath, base64Encoded);
    console.log(`Saved to: ${testFilePath}`);
    console.log('\n');
    
    console.log('✓ Test completed successfully!');
    console.log('\nTo test with the extension:');
    console.log(`1. Copy the test file: sudo cp ${testFilePath} /challenge/.config/.level_metadata`);
    console.log('2. Open VS Code and check logs at /home/hacker/cse240/.vscode/cp.dat');
    console.log('3. Open requirements panel and copy text to see prompts injected');
}

module.exports = {
    deriveKeyFromPassword,
    encryptFernet,
    decryptFernet
};
