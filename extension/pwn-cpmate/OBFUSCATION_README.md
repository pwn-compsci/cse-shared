# Code Obfuscation for Distribution

This extension uses code obfuscation to make it harder for students to reverse-engineer the monitoring functionality.

## How It Works

1. **Development**: Work with the normal, readable `extension.js` file
2. **Building**: Run `npm run build` to create an obfuscated version
3. **Packaging**: Run `./build_and_push.sh` which:
   - Obfuscates the code
   - Packages the extension into .vsix
   - Restores the original readable code for continued development

## Manual Commands

```bash
# Obfuscate code for distribution
npm run build

# Restore original readable code
npm run restore

# Full build + package + restore
npm run package
# OR
./build_and_push.sh
```

## What Gets Obfuscated

- Function names (except required exports like `activate`, `deactivate`)
- Variable names
- Removes all comments
- Minifies code (removes whitespace)
- Dead code elimination
- Multiple compression passes

## What Stays Readable

- Required VS Code API function names (`activate`, `deactivate`)
- Class names (for proper VS Code integration)
- Configuration loading functions that are referenced elsewhere

## File Management

- `extension.js` - Working file (readable during development)
- `extension.js.original` - Backup of original (created during build, excluded from .vsix)
- `build-obfuscate.js` - Obfuscation script (excluded from .vsix)
- `restore-original.js` - Restoration script (excluded from .vsix)

## Important Notes

1. **Always** run `npm run restore` if you manually run `npm run build` without packaging
2. The .vsix file contains the obfuscated code
3. The original readable code is never included in the distributed .vsix
4. `extension.js.original` is in .vscodeignore and won't be packaged
