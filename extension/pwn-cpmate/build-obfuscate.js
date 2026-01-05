#!/usr/bin/env node
/**
 * Build script for obfuscating extension.js before packaging
 * This keeps the source readable for development while making the distributed vsix harder to reverse-engineer
 */

const fs = require('fs');
const path = require('path');
const { minify } = require('terser');

const SOURCE_FILE = path.join(__dirname, 'extension.js');
const BACKUP_FILE = path.join(__dirname, 'extension.js.backup');
const BUILD_FILE = path.join(__dirname, 'extension.js.build');

async function obfuscate() {
    console.log('Starting code obfuscation...');
    
    try {
        // Read source file
        const sourceCode = fs.readFileSync(SOURCE_FILE, 'utf8');
        
        // Always backup the current source before obfuscating
        console.log('Creating backup of original extension.js...');
        fs.writeFileSync(BACKUP_FILE, sourceCode);
        
        // Obfuscate with terser
        console.log('Minifying and obfuscating code...');
        const result = await minify(sourceCode, {
            compress: {
                dead_code: true,
                drop_console: false, // Keep console logs for debugging if needed
                drop_debugger: true,
                keep_classnames: true,
                keep_fnames: false, // Rename functions for obfuscation
                passes: 2
            },
            mangle: {
                toplevel: false, // Don't mangle top-level function names (needed for VS Code API)
                keep_classnames: true,
                keep_fnames: false,
                reserved: ['activate', 'deactivate', 'loadLevelConfig', 'loadSessionConfiguration'] // Keep required exports
            },
            format: {
                comments: false, // Remove all comments
                beautify: false, // Minify output
                indent_level: 0
            },
            sourceMap: false
        });
        
        if (result.error) {
            throw result.error;
        }
        
        // Write obfuscated code to build file
        fs.writeFileSync(BUILD_FILE, result.code);
        
        // Swap: move source to backup, move build to source
        fs.renameSync(SOURCE_FILE, BACKUP_FILE);
        fs.renameSync(BUILD_FILE, SOURCE_FILE);
        
        const originalSize = sourceCode.length;
        const obfuscatedSize = result.code.length;
        const reduction = ((1 - obfuscatedSize / originalSize) * 100).toFixed(2);
        
        console.log(`✓ Obfuscation complete!`);
        console.log(`  Original size: ${originalSize} bytes`);
        console.log(`  Obfuscated size: ${obfuscatedSize} bytes`);
        console.log(`  Size reduction: ${reduction}%`);
        console.log(`  Backup saved to: ${BACKUP_FILE}`);
        
    } catch (error) {
        console.error('✗ Obfuscation failed:', error);
        process.exit(1);
    }
}

// Run if called directly
if (require.main === module) {
    obfuscate();
}

module.exports = { obfuscate };
