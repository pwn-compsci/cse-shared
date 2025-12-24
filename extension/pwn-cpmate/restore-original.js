#!/usr/bin/env node
/**
 * Restore original extension.js from backup after building
 * Run this after packaging to continue development with readable code
 */

const fs = require('fs');
const path = require('path');

const BACKUP_FILE = path.join(__dirname, 'extension.js.original');
const OUTPUT_FILE = path.join(__dirname, 'extension.js');

function restore() {
    if (!fs.existsSync(BACKUP_FILE)) {
        console.log('No backup file found. Nothing to restore.');
        return;
    }
    
    console.log('Restoring original extension.js from backup...');
    
    try {
        const backupCode = fs.readFileSync(BACKUP_FILE, 'utf8');
        fs.writeFileSync(OUTPUT_FILE, backupCode);
        console.log('✓ Original extension.js restored successfully!');
    } catch (error) {
        console.error('✗ Restoration failed:', error);
        process.exit(1);
    }
}

// Run if called directly
if (require.main === module) {
    restore();
}

module.exports = { restore };
