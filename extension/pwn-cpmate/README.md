# pwn-cpmate README

This Visual Studio Code extension enhances your development workflow by automating the process of creating uniquely named files based on pasted content, saving the newly created files in a designated history directory, and maintaining an efficient cache for future operations.

## Installation
For Visual Studio Code:
cd unique-file-paster
Install dependencies:
```bash
npm install
Package the extension:
```

```bash
vsce package
```

Install the extension manually:
Open Visual Studio Code.
Navigate to Extensions (sidebar > Extensions icon).
Click on "More Action" (...) > "Install from VSIX...".
Locate the packaged .vsix file and select it.

For code-server:
Transfer the .vsix file to your remote machine (if not already there).

Install the extension using command line:
```bash
code-server --install-extension unique-file-paster.vsix
```
## Usage
After installation, the extension will automatically handle pasting operations as configured. To manually trigger the functionality:

Open the command palette (Ctrl+Shift+P or Cmd+Shift+P on macOS).
Type Paste and Save and select the command.
The extension will handle the rest, creating a new file with pasted content and saving both files accordingly.

## Development
To contribute or modify the extension:

- Ensure prerequisites are installed.
- Navigate to the cloned repository and open it with VS Code.
- Make changes to the source files.
- Run locally:
    - Press F5 to open a new VS Code window with your extension running.
- Observe changes and debug if necessary.

## Troubleshooting
Ensure Node.js is updated to a version that supports all used features.
Verify that all dependencies are properly installed.
Check console logs for errors if the extension behaves unexpectedly.

## Requirements

- Unique File Creation: Automatically generates a unique filename for any pasted code, appending the appropriate extension based on the currently active file.
- Intelligent Directory Handling: Places newly created files in a history directory related to the current file, as determined by past interactions and stored entries.
- Automated File Management: Saves the current file immediately after pasting content into a new file, ensuring data integrity and immediate availability of all changes.

## Extension Settings

Include if your extension adds any VS Code settings through the `contributes.configuration` extension point.

For example:

This extension contributes the following settings:

* `myExtension.enable`: Enable/disable this extension.
* `myExtension.thing`: Set to `blah` to do something.

## Known Issues

Calling out known issues can help limit users opening duplicate issues against your extension.

## Release Notes

Users appreciate release notes as you update your extension.

### 1.0.0

Initial release of ...

### 1.0.1

Fixed issue #.

### 1.1.0

Added features X, Y, and Z.

---

## Working with Markdown

You can author your README using Visual Studio Code.  Here are some useful editor keyboard shortcuts:

* Split the editor (`Cmd+\` on macOS or `Ctrl+\` on Windows and Linux)
* Toggle preview (`Shift+Cmd+V` on macOS or `Shift+Ctrl+V` on Windows and Linux)
* Press `Ctrl+Space` (Windows, Linux, macOS) to see a list of Markdown snippets

## For more information

* [Visual Studio Code's Markdown Support](http://code.visualstudio.com/docs/languages/markdown)
* [Markdown Syntax Reference](https://help.github.com/articles/markdown-basics/)

**Enjoy!**
