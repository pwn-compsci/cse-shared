#!/usr/bin/env node

/**
 * Test script to decrypt and verify .level_metadata file
 */

const crypto = require('crypto');
const fernet = require('fernet');
const fs = require('fs');

const FERNET_PASSWORD = "why four out tho";

function deriveKeyFromPassword(password) {
    const hash = crypto.createHash('sha256');
    hash.update(password);
    const keyBytes = hash.digest();
    const base64 = keyBytes.toString('base64');
    const urlsafe = base64.replace(/\+/g, '-').replace(/\//g, '_');
    return urlsafe;
}

function decryptFernet(encryptedBase64, key) {
    try {
        // Decode from base64 to get the actual encrypted bytes
        const encryptedData = Buffer.from(encryptedBase64, 'base64').toString('utf8');
        
        // Create Fernet secret with the key
        const secret = new fernet.Secret(key);
        
        // Create Fernet token and decrypt
        const token = new fernet.Token({
            secret: secret,
            token: encryptedData,
            ttl: 0 // No TTL check
        });
        
        const decrypted = token.decode();
        return decrypted;
    } catch (error) {
        throw new Error(`Decryption failed: ${error.message}`);
    }
}

// Get file path from command line or use default
const filePath = process.argv[2] || '/cse/intro-to-programming-languages/23-proj-pointers/p23-level-01/.config/.level_metadata';

console.log('='.repeat(80));
console.log('Testing .level_metadata Decryption');
console.log('='.repeat(80));
console.log(`\nFile: ${filePath}\n`);

try {
    // Check if file exists
    if (!fs.existsSync(filePath)) {
        console.error(`❌ ERROR: File not found: ${filePath}`);
        process.exit(1);
    }
    
    console.log('✓ File exists');
    
    // Read file
    const fileContent = fs.readFileSync(filePath, 'utf8');
    console.log(`✓ File read (${fileContent.length} bytes)`);
    console.log(`\nFirst 100 chars: ${fileContent.substring(0, 100)}...`);
    
    // Derive key
    console.log('\n' + '-'.repeat(80));
    console.log('Deriving key from password...');
    const key = deriveKeyFromPassword(FERNET_PASSWORD);
    console.log(`✓ Key derived (${key.length} chars): ${key.substring(0, 30)}...`);
    
    // Decrypt
    console.log('\n' + '-'.repeat(80));
    console.log('Decrypting...');
    const decrypted = decryptFernet(fileContent.trim(), key);
    console.log(`✓ Decryption successful (${decrypted.length} bytes)`);
    console.log(`\nDecrypted preview: ${decrypted.substring(0, 100)}...`);
    
    // Check if it's still base64 encoded (double layer)
    let finalDecrypted = decrypted;
    if (decrypted.match(/^[A-Za-z0-9+/=]+$/)) {
        console.log('\n⚠️  Detected base64 encoding - decoding second layer...');
        finalDecrypted = Buffer.from(decrypted, 'base64').toString('utf8');
        console.log(`✓ Second base64 layer decoded (${finalDecrypted.length} bytes)`);
        console.log(`\nFinal preview: ${finalDecrypted.substring(0, 100)}...`);
    }
    
    // Parse JSON
    console.log('\n' + '-'.repeat(80));
    console.log('Parsing JSON...');
    const data = JSON.parse(finalDecrypted);
    console.log('✓ JSON parsed successfully');
    
    // Display structure
    console.log('\n' + '='.repeat(80));
    console.log('DECRYPTED CONTENT:');
    console.log('='.repeat(80));
    console.log(JSON.stringify(data, null, 2));
    
    // Summary
    console.log('\n' + '='.repeat(80));
    console.log('SUMMARY:');
    console.log('='.repeat(80));
    
    if (data.prompt_injections) {
        const injections = Object.keys(data.prompt_injections);
        console.log(`\nTotal injections: ${injections.length}`);
        console.log('\nInjections found:');
        
        injections.forEach(key => {
            const inj = data.prompt_injections[key];
            console.log(`\n  ${key}:`);
            console.log(`    Module: ${inj.module}`);
            console.log(`    Challenge: ${inj.challenge}`);
            console.log(`    Prompt length: ${inj.prompt ? inj.prompt.length : 0} chars`);
            console.log(`    Search for: "${inj.search_for}"`);
            console.log(`    Behavior check: ${inj.behavior_check}`);
            if (inj.prompt) {
                console.log(`    Prompt preview: ${inj.prompt.substring(0, 80)}...`);
            }
        });
    } else {
        console.log('\n⚠️  WARNING: No "prompt_injections" field found in data');
    }
    
    console.log('\n' + '='.repeat(80));
    console.log('✅ TEST PASSED - File is valid and decrypts correctly!');
    console.log('='.repeat(80));
    
} catch (error) {
    console.error('\n' + '='.repeat(80));
    console.error('❌ TEST FAILED');
    console.error('='.repeat(80));
    console.error(`\nError: ${error.message}`);
    console.error(`\nStack trace:\n${error.stack}`);
    process.exit(1);
}
