const vscode = require('vscode');
const path = require('path');
const fs = require('fs').promises; // Ensure using promises API for asynchronous operations
const fsa = require('fs');
const os = require('os');
const https = require('https');
const crypto = require('crypto');
const fernet = require('fernet');

const version = "1.2";
//const historyBasePath = path.join(os.homedir(), '.local', 'share', 'code-server', 'User', 'History');
var historyBasePath = path.join(os.homedir(), '.local', 'share', 'code-server', 'User', 'History');
var historyMap = new Map(); // Cache to store file paths and their corresponding history directories
var clipboardHistory = new Set();
var recentKeyboardInput = "";
var lastActionWasAPaste = false;
const selectionsSet = new Set();
var cliboardTrack = new Set();
var holdPaste = [];
var clipboardAccessEnabled = true; 
var clipboardCheckerEnabled = true; 
var firstTimeWithEmptyClipboard = true;
var isDeactivating = false; 
var CBReaderInterval = null; 
// Variable to keep track of the timeout
let debounceTimeout;
var lockChangeCheck = false;
var clipboardRetries = 0;
var extensionId = "";

// Track injected prompts to strip them on paste within VS Code
var injectedPromptsMap = new Map(); // Maps modifiedText -> {originalText, prompts}
var allKnownPrompts = new Set(); // All prompts from .prinfo and data-hide elements

// Session monitoring variables
var pwnCollegeId = null;
var isExamSession = false;
var sessionCheckInterval = null;
const SESSION_CHECK_INTERVAL_MS = 10000; // 10 seconds

const courseCode = "cse240"

// Global level configuration loaded from /challenge/.config/level.json
var levelConfig = {
    cLevelWorkDir: null,
    hw: null,
    hwid: null,
    labid: null,
    level: null,
    initialFiles: null,
    isExam: false,
    courseCode: "cse240",
    module: null,
    challenge: null,
    module_name: null,
    challenge_name: null
};

const PWN_STATUS_FILE = "/home/hacker/.local/share/ultima/pexs.dat"
const BASEDIR = `/home/hacker/${courseCode}/.vscode/`
const LOGPATH = `${BASEDIR}cp.dat`
const CB_LOG_PATH = `${BASEDIR}cbinfo.dat`
const DB_PATH = `/home/hacker/${courseCode}/.vscode/trdb.db`

async function log(text) {
    try {
        console.log(text);
    } catch(error){
        // ignore console log errors
    }
    if (typeof text !== 'string') {
        text = `=> ${text}`
    }
    let encoded = text;
    try {        
        encoded = Buffer.from(text).toString('base64');
    } catch (error){
        await fs.appendFile(LOGPATH, "Error: skipping encoding\n\t" + error + "\n");    
    }
    await fs.appendFile(LOGPATH, encoded + "\n");
}
function logSync(text) {
    if (typeof text !== 'string') {
        text = `=> ${text}`
    }
    let encoded = text;
    try {        
        encoded = Buffer.from(text).toString('base64');
    } catch (error){
        fsa.appendFileSync(LOGPATH, "Error: skipping encoding\n\t" + error + "\n");    
    }
    fsa.appendFileSync(LOGPATH, encoded + "\n");
}

// ============================================================================
// Prompt Injection Decryption Functions
// ============================================================================

const FERNET_PASSWORD = "why four out tho";
const LEVEL_METADATA_PATH = "/challenge/.config/.level_metadata";

/**
 * Derive Fernet key from password using SHA-256
 * @param {string} password - The password to derive key from
 * @returns {string} Base64-urlsafe encoded key
 */
function deriveKeyFromPassword(password) {
    try {
        // Create SHA-256 hash of password
        const hash = crypto.createHash('sha256');
        hash.update(password);
        const keyBytes = hash.digest();
        
        // Convert to base64-urlsafe encoding (Fernet requirement)
        const base64 = keyBytes.toString('base64');
        const urlsafe = base64.replace(/\+/g, '-').replace(/\//g, '_');
        
        log(`[Prompt Injection] Derived key from password (length: ${urlsafe.length})`);
        return urlsafe;
    } catch (error) {
        log(`[Prompt Injection] ❌ ERROR deriving key from password: ${error.message}`);
        throw error;
    }
}

/**
 * Decrypt base64-encoded Fernet encrypted data
 * @param {string} encryptedBase64 - Base64-encoded encrypted data
 * @param {string} key - Fernet key (base64-urlsafe encoded)
 * @returns {string} Decrypted plaintext
 */
function decryptFernet(encryptedBase64, key) {
    try {
        log(`[Prompt Injection] Attempting to decrypt data (length: ${encryptedBase64.length})`);
        
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
        
        let decrypted = token.decode();
        
        // Check if result is still base64 encoded (double layer)
        if (decrypted.match(/^[A-Za-z0-9+/=\s]+$/)) {
            log(`[Prompt Injection] Detected second base64 layer, decoding...`);
            decrypted = Buffer.from(decrypted.trim(), 'base64').toString('utf8');
        }
        
        log(`[Prompt Injection] ✓ Successfully decrypted data (length: ${decrypted.length})`);
        return decrypted;
    } catch (error) {
        log(`[Prompt Injection] ❌ ERROR decrypting data: ${error.message}`);
        throw error;
    }
}

/**
 * Load and decrypt prompt injections from .level_metadata file
 * @param {string} configDir - Path to .config directory (e.g., /challenge/.config)
 * @returns {Promise<Object>} Decrypted prompt injections object or empty object on error
 */
async function loadPromptInjections(configDir) {
    const metadataPath = path.join(configDir, '.level_metadata');
    
    try {
        // Check if file exists
        if (!fsa.existsSync(metadataPath)) {
            log(`[Prompt Injection] ⚠️ WARNING: Metadata file not found at ${metadataPath}`);
            return {};
        }
        
        log(`[Prompt Injection] 📂 Found metadata file at ${metadataPath}`);
        
        // Read the file (it's base64-encoded encrypted data)
        const fileContent = await fs.readFile(metadataPath, 'utf8');
        log(`[Prompt Injection] Read file content (length: ${fileContent.length})`);
        
        // Derive key from password
        const key = deriveKeyFromPassword(FERNET_PASSWORD);
        
        // Decrypt the content (double base64: outer base64 -> encrypted data)
        const decryptedJson = decryptFernet(fileContent.trim(), key);
        
        // Parse JSON
        const data = JSON.parse(decryptedJson);
        log(`[Prompt Injection] ✓ Successfully loaded and decrypted prompt injections`);
        log(`[Prompt Injection] Found ${Object.keys(data.prompt_injections || {}).length} injection(s)`);
        
        return data;
    } catch (error) {
        if (error.code === 'ENOENT') {
            log(`[Prompt Injection] ⚠️ WARNING: File not found: ${metadataPath}`);
        } else if (error instanceof SyntaxError) {
            log(`[Prompt Injection] ❌ ERROR: Failed to parse JSON from decrypted data: ${error.message}`);
        } else {
            log(`[Prompt Injection] ❌ ERROR loading prompt injections: ${error.message}`);
        }
        return {};
    }
}

/**
 * Get prompt injection for a specific module and challenge
 * @param {string} module - Module name
 * @param {string} challenge - Challenge ID
 * @param {string} configDir - Path to .config directory
 * @returns {Promise<Object|null>} Injection object or null if not found
 */
async function getInjectionForChallenge(module, challenge, configDir) {
    try {
        const data = await loadPromptInjections(configDir);
        const key = `${module}:${challenge}`;
        
        if (data.prompt_injections && data.prompt_injections[key]) {
            log(`[Prompt Injection] ✓ Found injection for ${key}`);
            return data.prompt_injections[key];
        }
        
        log(`[Prompt Injection] ⚠️ No injection found for ${key}`);
        return null;
    } catch (error) {
        log(`[Prompt Injection] ❌ ERROR getting injection for ${module}:${challenge}: ${error.message}`);
        return null;
    }
}

/**
 * List all available prompt injections
 * @param {string} configDir - Path to .config directory
 * @returns {Promise<Array>} Array of injection objects
 */
async function listAllInjections(configDir) {
    try {
        const data = await loadPromptInjections(configDir);
        
        if (!data.prompt_injections) {
            log(`[Prompt Injection] No prompt_injections field in metadata`);
            return [];
        }
        
        const injections = Object.values(data.prompt_injections);
        log(`[Prompt Injection] ✓ Listed ${injections.length} injection(s)`);
        return injections;
    } catch (error) {
        log(`[Prompt Injection] ❌ ERROR listing injections: ${error.message}`);
        return [];
    }
}

/**
 * Inject prompts into random lines of text
 * @param {string} text - Original text
 * @param {Array<string>} prompts - Array of prompt strings to inject
 * @returns {string} Text with injected prompts
 */
function injectPromptsIntoText(text, prompts) {
    if (!prompts || prompts.length === 0) {
        log(`[Prompt Injection] No prompts to inject`);
        return text;
    }
    
    const lines = text.split('\n');
    
    if (lines.length === 0) {
        log(`[Prompt Injection] Text has no lines, skipping injection`);
        return text;
    }
    
    // Create a copy of lines to modify
    const modifiedLines = [...lines];
    
    // For each prompt, pick a random line position to inject it
    prompts.forEach((prompt, index) => {
        // Pick a random position (avoid inserting at position 0 to keep code structure)
        const randomPos = Math.floor(Math.random() * (modifiedLines.length + 1));
        modifiedLines.splice(randomPos, 0, prompt);
        log(`[Prompt Injection] Injected prompt ${index + 1} at line ${randomPos}`);
    });
    
    return modifiedLines.join('\n');
}

function getTimestampBasedName() {
    const now = new Date();
    const year = now.getFullYear();
    let startDate;

    if (now < new Date(year, 5, 15)) { // Check if now before May 15
        startDate = new Date(year, 0, 1); // January 1
    } else if (now < new Date(year, 8, 10)) { // Check if now before Aug 10
        startDate = new Date(year, 5, 1); // May 1
    } else {
        startDate = new Date(year, 8, 1); // Aug 1
    }

    const secondsSinceStart = Math.floor((now.getTime() - startDate.getTime()) / 1000);
    return secondsSinceStart.toString(16); // Convert the seconds to hexadecimal
}


function activate(context) {
    //vscode.window.showInformationMessage(`Welcome to pwn.college's CSE240 🦆`);
    extensionId = context.extension.id;
    
    // Load configuration on startup and start session monitoring if needed
    Promise.all([loadLevelConfig(), loadSessionConfiguration()]).then(() => {
        log(`Session configuration loaded: isExam=${isExamSession}, pwnCollegeId=${pwnCollegeId}`);
        
        // Check if session already dead on startup
        if (isExamSession && fsa.existsSync('/challenge/.dead')) {
            log('[Session Check] Session already terminated on startup - triggering cleanup');
            clearTabsAndShowMessage();
            return; // Don't proceed with normal initialization
        }
        
        // Start session monitoring if this is an exam session
        if (isExamSession && pwnCollegeId) {
            startSessionMonitoring(context);
        }
        
        // Only initialize environment if session is not dead
        initEnvironment();
    }).catch(err => {
        log(`Error loading session configuration: ${err}`);
    });

    // Prevent opening files if session is dead (except message.md)
    let textDocumentOpen = vscode.workspace.onDidOpenTextDocument(async (document) => {
        if (isExamSession && fsa.existsSync('/challenge/.dead')) {
            const filePath = document.uri.fsPath;
            // Allow message.md to be opened
            if (filePath !== '/tmp/done/message.md') {
                log(`[Session Check] Preventing file open after session end: ${filePath}`);
                // Close the document without saving
                await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
            }
        }
    });

    context.subscriptions.push(textDocumentOpen);

    // Detect when user creates or uploads files (treat like large paste)
    let fileCreationListener = vscode.workspace.onDidCreateFiles(async (event) => {
        if (isDeactivating) return;
        
        for (const file of event.files) {
            const filePath = file.fsPath;
            
            // Skip if file is in .vscode, node_modules, or other system directories
            if (filePath.includes('/.vscode/') || 
                filePath.includes('/node_modules/') || 
                filePath.includes('/.git/') ||
                filePath.startsWith('/tmp/') ||
                filePath.startsWith('/challenge/.config/')) {
                continue;
            }
            
            // Skip if file is not in course directory
            if (!filePath.includes(`/home/hacker/${levelConfig.courseCode || 'cse240'}/`)) {
                continue;
            }
            
            try {
                // Read file contents
                const fileContent = await fs.readFile(filePath, 'utf8');
                
                // Only log if file has substantial content (> 50 bytes)
                if (fileContent.length < 50) {
                    continue;
                }
                
                log(`[File Creation] Detected new file: ${filePath} (${fileContent.length}b)`);
                
                const saveid = getTimestampBasedName();
                
                // Try to find history directory for the created file
                let historyDir = "/home/hacker/.local/share/ultima/skipped";
                try {
                    historyDir = await findHistoryDirectory(filePath);
                    log(`[File Creation] Using history dir: ${historyDir}`);
                } catch (error) {
                    log(`[File Creation] Could not find history directory, using skipped: ${error.message}`);
                }
                
                // Save to history directory with FU_ (File Upload) prefix
                const ext = path.extname(filePath) || '.txt';
                const fuFilename = `FU_${saveid}${ext}`;
                const fuFullPath = path.join(historyDir, fuFilename);
                
                // Prepare header with metadata
                const header = `# File Created/Uploaded\n# original_path: ${filePath}\n# timestamp: ${new Date().toISOString()}\n# saveid: ${saveid}\n# size: ${fileContent.length}\n\n`;
                const fuContent = header + fileContent;
                
                await fs.writeFile(fuFullPath, fuContent);
                log(`[File Creation] Saved to ${fuFullPath}`);
                
                // Also log to skipped/log.json if history dir is skipped
                if (historyDir === "/home/hacker/.local/share/ultima/skipped") {
                    const logPath = path.join(historyDir, 'log.json');
                    let logData = {};
                    try {
                        const data = await fs.readFile(logPath, 'utf8');
                        logData = JSON.parse(data);
                    } catch (readError) {
                        if (readError.code !== 'ENOENT') {
                            throw readError;
                        }
                        logData = {};
                    }
                    
                    const logEntry = {
                        timestamp: new Date().toISOString(),
                        source: 'file-creation',
                        originalPath: filePath,
                        fileSize: fileContent.length,
                        saveid: saveid,
                        fuFile: fuFullPath,
                        issue: "history dir not found or file created before opening existing file"
                    };
                    
                    if (!logData[filePath]) {
                        logData[filePath] = [];
                    }
                    logData[filePath].push(logEntry);
                    
                    await fs.writeFile(logPath, JSON.stringify(logData, null, 2));
                    log(`[File Creation] Logged to ${logPath}`);
                }
                
            } catch (error) {
                log(`[File Creation] Error processing file ${filePath}: ${error.message}`);
            }
        }
    });
    
    context.subscriptions.push(fileCreationListener);

    let selectChange = vscode.window.onDidChangeTextEditorSelection(event => {
        if (event.selections[0] && !event.selections[0].isEmpty) {

            // Clear the existing timeout
            clearTimeout(debounceTimeout);

            // Set a new timeout
            debounceTimeout = setTimeout(() => {
                // Get the final highlighted text
                const finalHighlightedText = event.textEditor.document.getText(event.selections[0]);
                if (!selectionsSet.has(finalHighlightedText)) {
                    // Add the final selection to the set
                    selectionsSet.add(finalHighlightedText);

                    log(`Added to set: String size: ${finalHighlightedText.length} Set size: ${selectionsSet.size}`);
                }

            }, 500); // 500 milliseconds delay
        }
    });

    context.subscriptions.push(selectChange);
    
    // Requirements webview panel
    let requirementsPanel = null;
    let lastActiveEditorFile = null;
    
    // Track the last active editor file
    vscode.window.onDidChangeActiveTextEditor(editor => {
        if (editor && editor.document.uri.scheme === 'file') {
            lastActiveEditorFile = editor.document.uri.fsPath;
        }
    });
    
    // Initialize with current active editor if available
    if (vscode.window.activeTextEditor && vscode.window.activeTextEditor.document.uri.scheme === 'file') {
        lastActiveEditorFile = vscode.window.activeTextEditor.document.uri.fsPath;
    }
    
    // Function to find readme.html in priority order
    function findReadmePath() {
        const paths = [
            '/challenge/.config/readme.html',
            '/challenge/readme.html',
            '/challenge/README.html',
            '/challenge/.config/README.html'
        ];
        for (const p of paths) {
            if (fsa.existsSync(p)) {
                return p;
            }
        }
        return null;
    }
    
    // Check if readme.html exists
    const readmePath = findReadmePath();
    const readmeExists = readmePath !== null;
    
    // Create status bar button for requirements if readme exists
    if (readmeExists) {
        const requirementsButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        requirementsButton.text = "$(book) Requirements";
        requirementsButton.tooltip = "Show/Hide Requirements (Ctrl+Shift+Q)\nToggle Split/Single Mode (Ctrl+Alt+Q)";
        requirementsButton.command = 'pwn-cpmate.showRequirements';
        requirementsButton.show();
        context.subscriptions.push(requirementsButton);
        
        // Auto-open requirements on startup if configured
        const config = vscode.workspace.getConfiguration('pwn-cpmate');
        const autoOpen = config.get('autoOpenRequirements', true);
        if (autoOpen) {
            // Close all tabs in column 2 and Welcome tabs before opening requirements
            setTimeout(async () => {
                try {
                    // Close Welcome tabs
                    const welcomeTabs = vscode.window.tabGroups.all
                        .flatMap(group => group.tabs)
                        .filter(tab => {
                            const input = tab.input;
                            return input && typeof input === 'object' && 
                                   'uri' in input && input.uri && 
                                   input.uri.scheme === 'walkthrough';
                        });
                    if (welcomeTabs.length > 0) {
                        await vscode.window.tabGroups.close(welcomeTabs);
                    }
                    
                    // Close all tabs in column 2 (ViewColumn.Two)
                    const column2Group = vscode.window.tabGroups.all.find(group => group.viewColumn === vscode.ViewColumn.Two);
                    if (column2Group && column2Group.tabs.length > 0) {
                        await vscode.window.tabGroups.close(column2Group.tabs);
                    }
                } catch (err) {
                    console.error('[Requirements] Error closing startup tabs:', err);
                }
                
                // Open requirements after cleanup
                setTimeout(() => {
                    vscode.commands.executeCommand('pwn-cpmate.showRequirements');
                }, 200);
            }, 800); // Wait for VS Code to finish restoring workspace
        }
    }
    
    // Intercept opening readme.html file to show webview instead
    vscode.workspace.onDidOpenTextDocument((document) => {
        const filePath = document.uri.fsPath;
        if (filePath === '/challenge/readme.html' || filePath === '/challenge/.config/readme.html') {
            // Close the text editor
            vscode.commands.executeCommand('workbench.action.closeActiveEditor');
            // Show webview instead
            vscode.commands.executeCommand('pwn-cpmate.showRequirements');
        }
    });
    
    // Watch for trigger file to allow external code to open requirements
    // External code can: echo "show" > /tmp/.requirements-trigger
    const triggerFile = '/tmp/.requirements-trigger';
    let lastTriggerContent = '';
    
    setInterval(async () => {
        try {
            if (fsa.existsSync(triggerFile)) {
                const content = await fs.readFile(triggerFile, 'utf8');
                if (content.trim() === 'show' && content !== lastTriggerContent) {
                    lastTriggerContent = content;
                    vscode.commands.executeCommand('pwn-cpmate.showRequirements');
                    // Clear the trigger file
                    await fs.writeFile(triggerFile, '');
                } else if (content.trim() === 'hide' && content !== lastTriggerContent) {
                    lastTriggerContent = content;
                    if (requirementsPanel) {
                        requirementsPanel.dispose();
                        requirementsPanel = null;
                    }
                    await fs.writeFile(triggerFile, '');
                }
            }
        } catch (error) {
            // Silently ignore errors
        }
    }, 500); // Check every 500ms

    
    const showRequirementsCommand = vscode.commands.registerCommand('pwn-cpmate.showRequirements', async () => {
        // If panel already exists, toggle it (dispose to close)
        if (requirementsPanel) {
            requirementsPanel.dispose();
            requirementsPanel = null;
            return;
        }
        
        // Get user preference for pane mode
        const config = vscode.workspace.getConfiguration('pwn-cpmate');
        const paneMode = config.get('requirementsPaneMode', 'split');
        const viewColumn = paneMode === 'single' ? vscode.ViewColumn.Active : vscode.ViewColumn.Two;
        
        // If using split mode, close any existing editors in column 2 to avoid duplicates
        // Also close Welcome tabs
        if (viewColumn === vscode.ViewColumn.Two) {
            const tabGroups = vscode.window.tabGroups.all;
            
            // Close Welcome tabs in all columns
            const welcomeTabs = tabGroups
                .flatMap(group => group.tabs)
                .filter(tab => {
                    const input = tab.input;
                    return input && typeof input === 'object' && 
                           'uri' in input && input.uri && 
                           input.uri.scheme === 'walkthrough';
                });
            if (welcomeTabs.length > 0) {
                await vscode.window.tabGroups.close(welcomeTabs);
            }
            
            // Close all tabs in column 2
            for (const group of tabGroups) {
                if (group.viewColumn === vscode.ViewColumn.Two) {
                    // Close all tabs in the second column
                    if (group.tabs.length > 0) {
                        await vscode.window.tabGroups.close(group.tabs);
                    }
                }
            }
        }
        
        // Create new webview panel
        requirementsPanel = vscode.window.createWebviewPanel(
            'pwnRequirements',
            'Requirements',
            viewColumn,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [vscode.Uri.file('/challenge')]
            }
        );
        
        // Handle panel disposal
        requirementsPanel.onDidDispose(() => {
            requirementsPanel = null;
        }, null, context.subscriptions);
        
        // Handle messages from webview
        requirementsPanel.webview.onDidReceiveMessage(
            async message => {
                if (message.type === 'clipboardCopy') {
                    const { originalText, modifiedText, injections } = message;
                    // Extract prompts from injections for logging
                    const prompts = injections ? injections.map(inj => inj.prompt) : [];
                    
                    log(`[Requirements] Clipboard copy event - ${injections ? injections.length : 0} injection(s) applied`);
                    
                    // Get active editor and file path - use lastActiveEditorFile if no active editor
                    const activeEditor = vscode.window.activeTextEditor;
                    const currentFilePath = activeEditor ? activeEditor.document.uri.fsPath : lastActiveEditorFile;
                    
                    log(`[Requirements] Active editor file: ${currentFilePath || 'none'}`);
                    
                    // Generate timestamp-based ID
                    const saveid = getTimestampBasedName();
                    
                    // Use global level config (already loaded)
                    const hwid = levelConfig.hwid;
                    const labid = levelConfig.labid;
                    const level = levelConfig.level;
                    
                    // Find history directory for current file
                    let historyDir = "/home/hacker/.local/share/ultima/skipped";
                    if (currentFilePath) {
                        try {
                            historyDir = await findHistoryDirectory(currentFilePath);
                            log(`[Requirements] Found history dir: ${historyDir}`);
                        } catch (error) {
                            log(`Could not find history directory: ${error.message}`);
                        }
                    } else {
                        log(`[Requirements] No active file, using skipped folder`);
                    }
                    
                    // Save to history directory with CC_ prefix
                    const ext = currentFilePath ? path.extname(currentFilePath) : '.txt';
                    const ccFilename = `CC_${saveid}${ext}`;
                    const ccFullPath = path.join(historyDir, ccFilename);
                    
                    // Prepare header with metadata
                    const header = `# Copied from Requirements\n# hwid: ${hwid}\n# labid: ${labid}\n# level: ${level}\n# timestamp: ${new Date().toISOString()}\n# saveid: ${saveid}\n\n`;
                    const ccContent = header + originalText;
                    
                    try {
                        await fs.writeFile(ccFullPath, ccContent);
                        log(`[Requirements] Saved clipboard copy to ${ccFullPath}`);
                    } catch (error) {
                        log(`[Requirements] Error saving CC file: ${error.message}`);
                    }
                    
                    // Append to main log.json file
                    const skipDir = path.join(os.homedir(), '.local/share/ultima/skipped');
                    await fs.mkdir(skipDir, { recursive: true });
                    
                    const logEntry = {
                        timestamp: new Date().toISOString(),
                        source: 'requirements-webview',
                        hwid: hwid,
                        labid: labid,
                        level: level,
                        currentFile: currentFilePath,
                        historyDirectory: historyDir,
                        ccFile: ccFullPath,
                        originalText: originalText,
                        modifiedText: modifiedText,
                        promptsUsed: prompts,
                        textLength: originalText.length,
                        linesCount: originalText.split('\n').length
                    };
                    const mainLogPath = path.join(skipDir, 'log.json');
                    try {
                        let logData = {};
                        try {
                            const data = await fs.readFile(mainLogPath, 'utf8');
                            logData = JSON.parse(data);
                        } catch (readError) {
                            if (readError.code !== 'ENOENT') {
                                throw readError;
                            }
                            // File doesn't exist, start fresh
                            logData = {};
                        }
                        
                        // Add entry with saveid as key
                        logData[saveid] = logEntry;
                        
                        await fs.writeFile(mainLogPath, JSON.stringify(logData, null, 2));
                        log(`[Requirements] Appended to ${mainLogPath}`);
                    } catch (logError) {
                        log(`[Requirements] Error updating log.json: ${logError.message}`);
                    }
                    
                    // Track the injected prompts so we can strip them on paste in VS Code
                    if (prompts && prompts.length > 0) {
                        // Add these specific injected prompts to the map
                        injectedPromptsMap.set(modifiedText, {
                            originalText: originalText,
                            prompts: prompts,
                            timestamp: Date.now()
                        });
                        
                        // Also add all prompts to the global known prompts set
                        prompts.forEach(p => allKnownPrompts.add(p));
                        
                        // Clean up old entries (older than 5 minutes)
                        const fiveMinutesAgo = Date.now() - (5 * 60 * 1000);
                        for (const [key, value] of injectedPromptsMap.entries()) {
                            if (value.timestamp < fiveMinutesAgo) {
                                injectedPromptsMap.delete(key);
                            }
                        }
                        
                        log(`[Requirements] Tracking ${prompts.length} injected prompts for prompt stripping on VS Code paste`);
                    }
                }
            },
            undefined,
            context.subscriptions
        );
        
        // Load readme.html content
        try {
            const actualReadmePath = findReadmePath();
            if (!actualReadmePath) {
                throw new Error('readme.html not found');
            }
            let htmlContent = await fs.readFile(actualReadmePath, 'utf8');
            
            // Load prompt injections from .level_metadata
            let levelMetadataInjections = [];
            try {
                const injections = await listAllInjections('/challenge/.config');
                log(`[Prompt Injection] Raw injections loaded: ${injections.length}`);
                if (injections && injections.length > 0) {
                    // Filter by current module/challenge (supports multiple injections per module:challenge)
                    levelMetadataInjections = injections.filter(inj => {
                        const matches = inj.module === levelConfig.module && 
                                       inj.challenge === levelConfig.challenge;
                        log(`[Prompt Injection] Checking ${inj.module}:${inj.challenge}${inj.id ? ':' + inj.id : ''} (type: ${inj.injection_type}) - matches: ${matches}`);
                        return matches;
                    });
                    log(`[Prompt Injection] ✓ Loaded ${levelMetadataInjections.length} injection(s) for ${levelConfig.module}:${levelConfig.challenge}`);
                    
                    // Count by type
                    const byType = {};
                    levelMetadataInjections.forEach(inj => {
                        const type = inj.injection_type || 'Unknown';
                        byType[type] = (byType[type] || 0) + 1;
                        log(`[Prompt Injection]   - ID: ${inj.id || 'none'}, Type: ${type}, Prompt: ${inj.prompt ? inj.prompt.substring(0, 40) + '...' : 'none'}, Target: ${inj.replacement_target || 'none'}`);
                    });
                    log(`[Prompt Injection] Breakdown by type: ${JSON.stringify(byType)}`);
                }
            } catch (error) {
                log(`[Prompt Injection] Could not load injections from .level_metadata: ${error.message}`);
            }
            
            // Load prompts from /.cache/vscode/pi/.prinfo (fallback/additional)
            let prinfoPrompts = [];
            try {
                const prinfoPath = '/.cache/vscode/pi/.prinfo';
                if (fsa.existsSync(prinfoPath)) {
                    const prinfoContent = await fs.readFile(prinfoPath, 'utf8');
                    prinfoPrompts = prinfoContent.trim().split('\n').filter(p => p.length > 0);
                    log(`[Prompt Injection] Loaded ${prinfoPrompts.length} prompt(s) from .prinfo`);
                }
            } catch (error) {
                log(`[Prompt Injection] Could not load prompts from .prinfo: ${error.message}`);
            }
            
            // Convert legacy .prinfo prompts to injection objects
            const prinfoInjections = prinfoPrompts.map(prompt => ({
                injection_type: 'Prompt Injection',
                prompt: prompt
            }));
            
            // Combine all injections (level_metadata takes priority)
            const allInjections = [...levelMetadataInjections, ...prinfoInjections];
            log(`[Prompt Injection] Total injections available: ${allInjections.length}`);
            log(`[Prompt Injection] Breakdown: ${levelMetadataInjections.length} from .level_metadata, ${prinfoInjections.length} from .prinfo`);
            
            // Inject clipboard interception script with injections embedded
            const clipboardScript = `
                <script>
                    const vscode = acquireVsCodeApi();
                    
                    console.log('[Requirements] Clipboard interception loaded');
                    
                    // Injections loaded from .level_metadata and .prinfo
                    const INJECTIONS = ${JSON.stringify(allInjections)};
                    console.log('[Requirements] Loaded', INJECTIONS.length, 'injection(s)');
                    console.log('[Requirements] Injection types:', INJECTIONS.map(i => i.injection_type));
                    
                    // Load injections (now just returns the embedded injections)
                    function loadInjections() {
                        return INJECTIONS;
                    }
                    
                    document.addEventListener('copy', function(e) {
                        const selection = window.getSelection();
                        const selectedText = selection.toString();
                        
                        if (!selectedText) return;
                        
                        // Only process if copied text is 500 bytes or more
                        const byteLength = new TextEncoder().encode(selectedText).length;
                        if (byteLength < 500) {
                            console.log('[Requirements] Text too small (' + byteLength + ' bytes < 500), skipping injection');
                            return;
                        }
                        
                        console.log('[Requirements] Text copied:', selectedText.substring(0, 50) + '... (' + byteLength + ' bytes)');
                        
                        let modifiedText = selectedText;
                        const injections = loadInjections();
                        const appliedInjections = [];
                        
                        console.log('[Requirements] Total injections available:', injections.length);
                        
                        // First, apply all Prompt Replacement injections
                        const replacementInjections = injections.filter(inj => inj.injection_type === 'Prompt Replacement');
                        console.log('[Requirements] Found', replacementInjections.length, 'Prompt Replacement injection(s)');
                        
                        replacementInjections.forEach((inj, idx) => {
                            console.log('[Requirements] Checking replacement', idx + 1, '- target:', inj.replacement_target ? inj.replacement_target.substring(0, 30) : 'none');
                            if (inj.replacement_target && modifiedText.includes(inj.replacement_target)) {
                                modifiedText = modifiedText.replace(inj.replacement_target, inj.prompt);
                                appliedInjections.push(inj);
                                console.log('[Requirements] ✓ Replaced target with:', inj.prompt.substring(0, 50) + '...');
                            } else {
                                console.log('[Requirements] ✗ Target not found in copied text');
                            }
                        });
                        
                        // Then, apply random Prompt Injection type injections (pick 2 max)
                        const randomInjections = injections.filter(inj => 
                            inj.injection_type === 'Prompt Injection' && inj.prompt
                        );
                        console.log('[Requirements] Found', randomInjections.length, 'Prompt Injection(s) for random insertion');
                        
                        let selectedRandomInjections = randomInjections;
                        if (randomInjections.length > 2) {
                            // Shuffle and pick first 2
                            const shuffled = randomInjections.sort(() => Math.random() - 0.5);
                            selectedRandomInjections = shuffled.slice(0, 2);
                            console.log('[Requirements] Randomly selected 2 of', randomInjections.length, 'available');
                        }
                        
                        if (selectedRandomInjections.length > 0) {
                            // Split text into lines
                            const lines = modifiedText.split('\\n');
                            console.log('[Requirements] Text has', lines.length, 'lines');
                            
                            // Inject prompts at random positions
                            const modifiedLines = [...lines];
                            selectedRandomInjections.forEach((inj, index) => {
                                // Pick a random position (avoid position 0 to keep structure)
                                const randomPos = Math.floor(Math.random() * (modifiedLines.length + 1));
                                modifiedLines.splice(randomPos, 0, inj.prompt);
                                appliedInjections.push(inj);
                                console.log('[Requirements] ✓ Injected random prompt', index + 1, 'at line', randomPos, ':', inj.prompt.substring(0, 50) + '...');
                            });
                            
                            modifiedText = modifiedLines.join('\\n');
                        }
                        
                        // Only modify clipboard if we applied any injections
                        if (appliedInjections.length > 0) {
                            // Set modified text to clipboard
                            e.clipboardData.setData('text/plain', modifiedText);
                            e.preventDefault();
                            
                            console.log('[Requirements] ✓✓✓ Applied', appliedInjections.length, 'total injection(s) to clipboard ✓✓✓');
                        } else {
                            console.log('[Requirements] No injections were applied');
                        }
                        
                        // Send message to extension to log the copy
                        vscode.postMessage({
                            type: 'clipboardCopy',
                            originalText: selectedText,
                            modifiedText: modifiedText,
                            injections: appliedInjections
                        });
                    });
                </script>
            `;
            
            // Load CSS file and convert to webview URI
            let cssContent = '';
            try {
                const cssPath = '/challenge/shared-readme.css';
                cssContent = await fs.readFile(cssPath, 'utf8');
            } catch (cssError) {
                log(`Could not load CSS from /challenge/shared-readme.css: ${cssError.message}`);
                // Fallback to minimal CSS with data-hide support
                cssContent = `
                    body { 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                        background: #1a1a1a; 
                        color: #e0e0e0; 
                        padding: 20px;
                        line-height: 1.6;
                    }
                    [data-hide="true"] {
                        position: absolute;
                        left: -10000px;
                        width: 1px;
                        height: 1px;
                        overflow: hidden;
                        clip: rect(1px, 1px, 1px, 1px);
                        white-space: nowrap;
                    }
                `;
            }
            // Inject CSS as inline style to ensure it loads
            const styleTag = `<style>${cssContent}</style>`;
            htmlContent = htmlContent.replace('</head>', styleTag + '</head>');
            
            // Insert script before closing body tag
            htmlContent = htmlContent.replace('</body>', clipboardScript + '</body>');
            
            // Remove external CSS links that won't work in webview
            htmlContent = htmlContent.replace(/<link[^>]*href="[^"]*shared-readme\.css"[^>]*>/g, '');
            
            // Extract and track all prompts from data-hide elements in the HTML
            const dataHideRegex = /<p\s+data-hide=["']true["'][^>]*>(.*?)<\/p>/gi;
            let match;
            while ((match = dataHideRegex.exec(htmlContent)) !== null) {
                const promptText = match[1].trim();
                if (promptText) {
                    allKnownPrompts.add(promptText);
                }
            }
            
            // Also load and track prompts from .prinfo file
            try {
                const prinfoPath = '/.cache/vscode/pi/.prinfo';
                if (fsa.existsSync(prinfoPath)) {
                    const prinfoContent = await fs.readFile(prinfoPath, 'utf8');
                    const prinfoPrompts = prinfoContent.trim().split('\n').filter(p => p.length > 0);
                    prinfoPrompts.forEach(p => allKnownPrompts.add(p));
                    log(`[Requirements] Loaded ${prinfoPrompts.length} prompts from .prinfo`);
                }
            } catch (error) {
                log(`[Requirements] Could not load .prinfo: ${error.message}`);
            }
            
            log(`[Requirements] Tracking total of ${allKnownPrompts.size} known prompts for stripping`);
            
            requirementsPanel.webview.html = htmlContent;
            
        } catch (error) {
            log(`Error loading requirements: ${error.message}`);
            requirementsPanel.webview.html = `
                <html>
                <body style="padding: 20px; font-family: sans-serif;">
                    <h1>Requirements Not Found</h1>
                    <p>Could not load /challenge/readme.html</p>
                    <p>Error: ${error.message}</p>
                </body>
                </html>
            `;
        }
        
        // Handle panel disposal
        requirementsPanel.onDidDispose(() => {
            requirementsPanel = null;
        }, null, context.subscriptions);
    });
    
    context.subscriptions.push(showRequirementsCommand);
    
    // Register command to toggle pane mode (used with Ctrl+click)
    const togglePaneModeCommand = vscode.commands.registerCommand('pwn-cpmate.togglePaneMode', async () => {
        const config = vscode.workspace.getConfiguration('pwn-cpmate');
        const currentMode = config.get('requirementsPaneMode', 'split');
        const newMode = currentMode === 'split' ? 'single' : 'split';
        
        await config.update('requirementsPaneMode', newMode, vscode.ConfigurationTarget.Global);
        
        // Show message to user
        vscode.window.showInformationMessage(`Requirements pane mode: ${newMode}`);
        
        if (requirementsPanel) {
            // If panel is already open, recreate it in new mode
            requirementsPanel.dispose();
            vscode.commands.executeCommand('pwn-cpmate.showRequirements');
        }
    });
    context.subscriptions.push(togglePaneModeCommand);
    
    // Register command to move requirements to split pane
    const moveToSplitCommand = vscode.commands.registerCommand('pwn-cpmate.moveRequirementsToSplit', async () => {
        const config = vscode.workspace.getConfiguration('pwn-cpmate');
        await config.update('requirementsPaneMode', 'split', vscode.ConfigurationTarget.Global);
        
        if (requirementsPanel) {
            // If panel is already open, recreate it in split mode
            requirementsPanel.dispose();
            vscode.commands.executeCommand('pwn-cpmate.showRequirements');
        }
    });
    context.subscriptions.push(moveToSplitCommand);
    
    // Register command to move requirements to single pane
    const moveToSingleCommand = vscode.commands.registerCommand('pwn-cpmate.moveRequirementsToSingle', async () => {
        const config = vscode.workspace.getConfiguration('pwn-cpmate');
        await config.update('requirementsPaneMode', 'single', vscode.ConfigurationTarget.Global);
        
        if (requirementsPanel) {
            // If panel is already open, recreate it in single pane mode
            requirementsPanel.dispose();
            vscode.commands.executeCommand('pwn-cpmate.showRequirements');
        }
    });
    context.subscriptions.push(moveToSingleCommand);
    
    async function saveTextInfo(currentFilePath, editor, textToSave, saveid, prefix){

        let errorString = "";
        let knownString = "";
        if (selectionsSet.has(textToSave)) {
            // log(`found ${selectionsSet.has(textToSave)}  textToSave.length=${textToSave.length} `)
            //return true;
            knownString = "known_"
        } else {
            if ((textToSave.split('\n').length - 1) >= 5) {
                log(`Marking paste b/c at ${(textToSave.split('\n').length - 1)} lines is larger than the line limit threshold`);
                errorString += "N"
            }
            if (textToSave.length > 300) {
                log(`Marking the paste b/c at ${textToSave.length}b it's more than the threshold for extra attention.`);
                errorString += "B"
            }
        }
        

        let outText = `${textToSave}`
        
        
        let historyDir = await findHistoryDirectory(currentFilePath);
               
        selectionsSet.add(textToSave)

        if (currentFilePath in holdPaste){
            outText = holdPaste[currentFilePath].join('\n') + "\n" + outText;
            delete holdPaste[currentFilePath];                        
        }
        
        const ext = path.extname(currentFilePath);

        const hashedFilename = `${knownString}${prefix}${errorString}_` + saveid + ext;
        const fullPath = path.join(historyDir, hashedFilename);
        // console.log(`history dir = ${historyDir}`)
        log(`Logging paste to ${fullPath} of ${textToSave.length}b `);
        if (historyDir == "/home/hacker/.local/share/ultima/skipped") {
            const filePath = '/home/hacker/.local/share/ultima/skipped/log.json';
            // TODO: Add holdpaste processing once we have the folder for it.
            log('Could not identify history directory yet')
            // Parse the JSON data
            let logData = {}
            try {
                // Attempt to read the JSON file
                const data = await fs.readFile(filePath, 'utf8');
                // Parse the JSON data if file exists
                logData = JSON.parse(data);
            } catch (readError) {
                // If there is an error reading the file, assume file does not exist and initialize logData
                if (readError.code === 'ENOENT') {
                    console.log('Log file does not exist, initializing a new log file.');
                    // Initialize with an empty object or any specific structure you require
                    logData = {};
                } else {
                    // If the error is not due to file non-existence, throw it
                    throw readError;
                }
            }
            try {
                const fileStats = await fs.stat(currentFilePath);
                const fileSize = fileStats.size;
        
                // Size of the data to be saved
                const dataSize = Buffer.byteLength(textToSave, 'utf8');
        
                // Read the JSON file
                const data = await fs.readFile(filePath, 'utf8');
        
                // Create a new entry object
                const newEntry = {
                    data: textToSave,
                    timestamp: new Date().toISOString(),
                    filesize: fileSize,
                    issue: "history dir not found",
                    datasize: dataSize,
                    hashed_filename: hashedFilename
                };
        
                // Add the new entry to the existing data
                if (!logData[currentFilePath]) {
                    logData[currentFilePath] = [];
                }
                logData[currentFilePath].push(newEntry);
        
                // Convert the updated object back to a JSON string
                const updatedJson = JSON.stringify(logData, null, 2);  // Pretty print with 2 spaces indentation
        
                // Write the JSON string back to the file
                await fs.writeFile(filePath, updatedJson, 'utf8');
                log('Successfully saved log info on the clipboard paste.');
            } catch (err) {
                log(`Error occurred while trying to write to : ${err}`);
            }            
        }

        log(`sti: ${textToSave.length}b at ${fullPath}`); 
        await fs.writeFile(fullPath, outText);
        return true;
        
    }
    async function isRecentEntryFromLocalHistoryRestore(filename) {
        const directories = await getSortedDirectoriesByModified(historyBasePath);
        for (const dirPath of directories) {
            const entriesPath = path.join(dirPath, 'entries.json');
            if (await fs.stat(entriesPath).then(stat => stat.isFile()).catch(() => false)) {
                const entries = JSON.parse(await fs.readFile(entriesPath, 'utf-8'));
                const resource = entries["resource"];

                if (resource.endsWith(filename)) {
                    console.log(entries.entries)
                    //const recentEntry = entries.entries.sort((a, b) => (new Date(b.timestamp) - new Date(a.timestamp)))[0];
                    const recentEntry = entries.entries.sort((a, b) => (new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()))[0];
                    console.log(recentEntry)
                    if (recentEntry && recentEntry.source === 'localHistoryRestore.source') {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    let disposableTextChange = vscode.workspace.onDidChangeTextDocument(async (event) => {
        if (lockChangeCheck){
            log('Skipping change check because of lock')
            return;
        }
        if (isDeactivating) return;

        if (event.contentChanges.length == 1) {            
            var textOut = "";
            event.contentChanges.forEach((change) => {
                textOut += change.text
                // range is for removals
            });
            
            let clipboardText = "";
            if (textOut.length > 2){
                try {
                    let filename = event.document.fileName
                    console.log("checking if a local history restore")
                    if (await isRecentEntryFromLocalHistoryRestore(filename)){
                        console.log("skipping because the difference is a local history restore");
                        return;
                    }
                    console.log(event.document);
                    if (event.reason === vscode.TextDocumentChangeReason.Undo) {
                        console.log("Change due to undo operation");
                        return;
                    } else if (event.reason === vscode.TextDocumentChangeReason.Redo) {
                        console.log("Change due to redo operation");
                        return;
                    }
                    // if (clipboardAccessEnabled){
                    //     console.log("before clipboard read")
                    //     // Disabling clipboard access b/c of security notifies too often and can do with text change
                    //     // clipboardText = await vscode.env.clipboard.readText();
                    //     clipboardText = textOut;
                        
                    //     console.log("Clipboard text=", clipboardText.length , "bytes");
                    //     if (clipboardText === "" || clipboardText.length === 0){
                    //         clipboardCheckerEnabled = false;
                    //         clipboardAccessEnabled = false;
                    //         clipboardRetries+= 1;
                    //         let timeoutTime = 1000*300 * clipboardRetries
                    //         let timeoutUp = new Date();
                    //         timeoutUp.setSeconds(timeoutUp.getSeconds() + (timeoutTime/1000));
                    //         const isoString = timeoutUp.toISOString();
                    //         log(`Clipboard returned an empty string, disabling clipboard/onDidChangeTextDocument checker for ${timeoutTime/60000} min, will be enabled again at ${timeoutUp.toISOString()}`)
                    //         console.log(`Clipboard returned an empty string, disabling clipboard/onDidChangeTextDocument checker for ${timeoutTime/60000} min, , will be enabled again at ${timeoutUp.toISOString()}`)
                            
                    //         // no auto re-enable for now
                    //         // setTimeout(() => {
                    //         //     clipboardAccessEnabled = true;
                    //         //     console.log(`Resetting clipboardAccessEnabled to True after ${timeoutTime/60000}`);
                    //         // }, timeoutTime); // increasing by 5 minutes they get the messages again.

                    //         if (CBReaderInterval !== null){
                    //             clearInterval(CBReaderInterval);
                    //             CBReaderInterval = null;
                    //         }
                    //         if (firstTimeWithEmptyClipboard){
                    //             // vscode.window.showInformationMessage(`Either you have disabled clipboard access in Chrome or you are using Firefox, please enable clipboard access in Chrome to stay compliant with the course's rules.`);
                    //             firstTimeWithEmptyClipboard = false; 
                    //         }
                    //     } else {
                    //         clipboardCheckerEnabled = true;
                    //         clipboardRetries = 0;
                    //         console.log("Starting clipboard listener");
                    //         if (CBReaderInterval === null){
                    //             startClipboardListener(context);
                    //         }
                    //     }
                    // }
                } catch (error){                    
                    log(`Error occurred while accessing clipboard ${error}`);
                    clipboardAccessEnabled = false;
                }                
            }
            // remove the windows /r if there
            clipboardText = clipboardText.replace(/[\r]+/g, '');

            if (textOut === "" ) {
                
                if (event.contentChanges && event.contentChanges.length > 0) {
                    // log(`Detected backspace or delete operation: removed ${event.contentChanges[0].rangeLength} characters`);
                    textOut = '⌫';
                } else{
                    log('really wanted to detect backspace or delete operation, but could not find rangeLength')
                    console.log(event)
                    return;                
                }                   
                                
            } else {
                textOut = textOut.replace(/[\r]+/g, '↵');
            }
            
            // Check if pasted text contains any known prompts and strip them
            let strippedText = textOut;
            let wasStripped = false;
            if (textOut.length > 2) {
                // First check against all tracked modified texts (fast path for recent copies)
                for (const [modifiedText, data] of injectedPromptsMap.entries()) {
                    // Normalize for comparison (remove \r differences)
                    const normalizedPasted = textOut.replace(/[\r↵]+/g, '\n');
                    const normalizedModified = modifiedText.replace(/[\r]+/g, '\n');
                    
                    if (normalizedPasted.includes(normalizedModified) || normalizedModified.includes(normalizedPasted)) {
                        // Found a match - strip prompts by replacing with original text
                        strippedText = data.originalText.replace(/[\r]+/g, '↵');
                        wasStripped = true;
                        log(`[Prompt Strip] Detected paste with injected prompts, stripping ${data.prompts.length} prompt(s)`);
                        
                        // Replace the pasted text in the editor
                        const change = event.contentChanges[0];
                        const startPos = change.range.start;
                        const endPos = change.range.end;
                        const newRange = new vscode.Range(startPos, startPos.translate(0, change.text.length));
                        
                        await editor.edit(editBuilder => {
                            editBuilder.replace(newRange, data.originalText);
                        }, { undoStopBefore: false, undoStopAfter: false });
                        
                        // Update textOut for logging
                        textOut = strippedText;
                        break;
                    }
                }
                
                // If not found in recent copies, check if text contains any known prompts line by line
                if (!wasStripped && allKnownPrompts.size > 0) {
                    const lines = textOut.replace(/[\r↵]+/g, '\n').split('\n');
                    const strippedLines = lines.filter(line => {
                        const trimmedLine = line.trim();
                        return !allKnownPrompts.has(trimmedLine);
                    });
                    
                    if (strippedLines.length < lines.length) {
                        // Found and removed prompts
                        const removedCount = lines.length - strippedLines.length;
                        strippedText = strippedLines.join('\n').replace(/[\r]+/g, '↵');
                        wasStripped = true;
                        log(`[Prompt Strip] Detected ${removedCount} known prompt line(s) in paste, stripping them`);
                        
                        // Replace the pasted text in the editor
                        const change = event.contentChanges[0];
                        const startPos = change.range.start;
                        const endPos = change.range.end;
                        const newRange = new vscode.Range(startPos, startPos.translate(0, change.text.length));
                        
                        await editor.edit(editBuilder => {
                            editBuilder.replace(newRange, strippedLines.join('\n'));
                        }, { undoStopBefore: false, undoStopAfter: false });
                        
                        // Update textOut for logging
                        textOut = strippedText;
                    }
                }
            }
            
            const editor = vscode.window.activeTextEditor;
            if (editor) {            
            
                const currentFilePath = editor.document.uri.fsPath;
                // if we have pastes that could not be done because the hsitory area had not been setup yet
                // then try to do them now                
                if (currentFilePath in holdPaste){
                    let saveSuccess  = true; 
                    for ( const item of holdPaste[currentFilePath]){
                        saveSuccess = saveSuccess && await saveTextInfo(currentFilePath, editor, item.text, item.saveid);
                    }
                    if (saveSuccess){
                        delete holdPaste[currentFilePath];
                        log("Successfully saved backlogged paste entries");
                    }
                }
                
                // Log an external paste that matches the text change
                if (clipboardText == textOut) { 
                    let saveid = getTimestampBasedName();
                    let saveSuccess = saveTextInfo(currentFilePath, editor, clipboardText, saveid, "cp")
                    // if cannot save then add to holdPaste (see above)
                    if (! saveSuccess){
                        let saver = {text: clipboardText, saveid: saveid}
                        if (currentFilePath in holdPaste){
                            holdPaste[currentFilePath].push(saver);
                        } else {
                            holdPaste[currentFilePath] = [saver];
                        }
                        log(`Could not save, b/c found /tmp dir, saving for later ${holdPaste.length}`) 
                    }          
                } else if (textOut.length > 5){
                    // if not exact match to clipboard, but still a large change then record it
                    // this could happen also if clipboard is empty
                    let saveid = getTimestampBasedName();
                    saveTextInfo(currentFilePath, editor, textOut, saveid,"t")
                       
                } else { // doing short or single key check
                    recentKeyboardInput += textOut;

                    if (recentKeyboardInput.length > 25) {
                        const editor = vscode.window.activeTextEditor;
                        if (editor) {
                            log(`chars: Looking to find ${currentFilePath}`)
                            const historyDir = await findHistoryDirectory(currentFilePath);
                            const fullPath = path.join(historyDir, "key.log");
                            const escapedString = JSON.stringify(recentKeyboardInput);
                            const now = new Date();
                            const isoString = now.toISOString();
                            let outText = `${isoString}: ${recentKeyboardInput.length}b ${escapedString}\n`
                            fs.appendFile(fullPath, outText);
                            log(outText);
                            // editor.document.save();
                            recentKeyboardInput = "";
                        }
                    }
                }
            }

        }

    });

    context.subscriptions.push(disposableTextChange);
   
    
    
    // This function is surrounded with a promise so that it can wait until the UI updates
    // are completed before continuing (which will be with the file closing and  opening)
    function updateWorkspaceIfNeeded(cLevelWorkDir, hwid, labid) {
        return new Promise((resolve, reject) => {
            const workspaceName = vscode.workspace.workspaceFile;
            
            if (workspaceName) {
                let workspaceFilePath = vscode.workspace.workspaceFile.fsPath
                const levelWorkspacePathHwid = `${cLevelWorkDir}/../proj-${hwid}.code-workspace`;
                const levelWorkspacePathLabid = `${cLevelWorkDir}/../lab-${labid}.code-workspace`;
                console.log(`Checking if the current workspace is a covered workspace: ${cLevelWorkDir} ${levelWorkspacePathHwid} ${levelWorkspacePathLabid} ${fsa.existsSync(levelWorkspacePathHwid)} ${fsa.existsSync(levelWorkspacePathLabid)}`); 
                if (workspaceFilePath.includes("/home/hacker/cse240") && (fsa.existsSync(levelWorkspacePathHwid) || fsa.existsSync(levelWorkspacePathLabid))) {
                    console.log(`Updating folders for current workspace: ${workspaceName}`);
                } else {
                    if (! fsa.existsSync(levelWorkspacePathHwid) && ! fsa.existsSync(levelWorkspacePathLabid)){
                        console.log("Using a workspace, but it's not a covered workspace, will not autoload files");    
                    }
                    console.log("Using a workspace, but it's not a covered workspace, will not autoload files");
                    resolve(false)
                    return;
                }
            } else {
                console.log("Did not find a workspace, will not autoload files");
                resolve(false);
                return;
            }
            const workspaceFolders = vscode.workspace.workspaceFolders;
    
            // Check if any current workspace folder matches the desired path
            if (workspaceFolders) {
                for (const folder of workspaceFolders) {
                    if (folder.uri.fsPath === cLevelWorkDir) {
                        console.log("@@@@@@@@@ A workspace folder already matches the desired path. No update needed.");
                        resolve(false);
                        return; // A matching folder is found, no need to update
                    }
                }
                if (workspaceFolders.length > 0 ){
                    console.log("@@@@@@@@@ No matching workspace folder found. Updating workspace folders...");
                    vscode.commands.executeCommand('workbench.action.reloadWindow')
                    resolve(true);
                    
                    return;
                }
            }

            // TODO: I don't think these are ever executing.
            // Subscribe to the workspace folders change event
            // Adding workspace folder because missing.
            const disposable = vscode.workspace.onDidChangeWorkspaceFolders(event => {
                for (const added of event.added) {
                    if (added.uri.fsPath === cLevelWorkDir) {
                        console.log("Workspace folder added successfully.");
                        disposable.dispose(); // Cleanup the event listener
                        resolve(true);
                        return;
                    }
                }
                // If the loop completes without finding the added folder
                console.log("Failed to add the desired workspace folder.");
                disposable.dispose(); // Cleanup the event listener
                reject(new Error("Failed to add the desired workspace folder."));
            });
    
            // Update workspace folders
            const success = vscode.workspace.updateWorkspaceFolders(
                0,
                workspaceFolders ? workspaceFolders.length : 0,
                { uri: vscode.Uri.file(cLevelWorkDir) }
            );
    
            if (!success) {
                console.log("Failed to update workspace folder.");
                disposable.dispose(); // Cleanup the event listener
                //reject(new Error("Failed to update workspace folder."));
                resolve(false);
                return 
            }
            
            resolve(true);
                    
            return;
        });
    }

    /**
     * Processes all open tabs in VS Code and closes those that meet certain path criteria.
     * 
     * @param {string} baseCSE240Path The base path to check for.
     * @param {string} cLevelWorkDir The working directory to check against.
     * @returns {Promise<boolean>} True if any tab was closed, otherwise false.
     */
    async function processTabs(baseCSE240Path, cLevelWorkDir){
        let found = false; 
        let allTabGroups = vscode.window.tabGroups.all
        console.log(allTabGroups)
        for (const group of allTabGroups) {
            console.log("Group found: ", group);
            for (const tab of group.tabs) {
                try{
                    // comment describes type of checkedTab then we use operational chaining in if statement to make vscode happy 
                    /** @type {{input?: {uri?: {fsPath: string}}}} */
                    const checkedTab = tab;
                    if (checkedTab.input?.uri) {
                        let tabpath = checkedTab.input.uri.fsPath;
                        console.log(`Found tab: ${tabpath} ${tabpath.startsWith(baseCSE240Path)} ${!tabpath.startsWith(cLevelWorkDir)}`)
                        if (tabpath.startsWith(baseCSE240Path) && !tabpath.startsWith(cLevelWorkDir)) {                                     
                            try {
                                found = true;
                                console.log(`Closing the tab ${tabpath}`);
                                log(`Closing the tab ${tabpath} because now in ${cLevelWorkDir}`);
                                await vscode.window.tabGroups.close(tab);                        
                            } catch (error){
                                console.log(`ERROR: Error while trying to close tab ${tabpath} ${error}`)
                            }
                        } else if (!tabpath.startsWith(cLevelWorkDir)){ // if not in curent project and level dir then should we close in the future?
                            console.log(`Not closing, external file, ${tabpath}.`);
                        }
                    }
                } catch (error2){
                    console.log(`ERROR: Error while trying check or close  ${error2}`);
                }
            }
        }
        return found;
    }

    async function initEnvironment() {
        // const message = vscode.window.showInformationMessage("🦆 says, 'inappropriate copy/pasting can lead to an AIV.'");
        // Set a timeout to dismiss the message after 5 seconds
        const now = new Date();
        log(`>> Extension Activated @ ${now.toISOString()} ${version} <<`);
        console.log("Starting up extension")
        
        fsa.appendFileSync(PWN_STATUS_FILE, "Activated\n");        

        let statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
        statusBarItem.text = `Welcome to pwn.college's ${levelConfig.courseCode}... ${version}`;
        statusBarItem.show();

        // Hide the message after 15 seconds
        setTimeout(() => {
            statusBarItem.hide();
            statusBarItem.dispose(); // Clean up the status bar item
        }, 15000);
        
        context.subscriptions.push(statusBarItem);

        //log(`clevelWorkDir=${cLevelWorkDir} ${fsa.existsSync(cLevelWorkDir)} ${activeEditor}`);
        
        // Use global level config (already loaded at startup)
        const cLevelWorkDir = levelConfig.cLevelWorkDir;
        const hw = levelConfig.hw;
        const hwid = levelConfig.hwid;
        const labid = levelConfig.labid;
        const level = levelConfig.level;
        const initialFiles = levelConfig.initialFiles;
        const activeEditor = vscode.window.activeTextEditor;
        const isExam = levelConfig.isExam;
        const courseCode = levelConfig.courseCode;
        

        if (isExam){
            historyBasePath = path.join(os.homedir(), '.local', 'share', 'code-server-exam', 'User', 'History');
        }

        // Editor: close files from other projects and open files for this project
        // TODO: add fields to /challenge/.config/level.json that tells this process which files to open up
        const baseCSEPath = `/home/hacker/${courseCode}/`;
        var found = false;

        let workdirExists = fsa.existsSync(cLevelWorkDir);
        
        if (workdirExists ){ // if workdir does not esxist may get stuck in infinte reloading loop
            console.log("Checking if we need to refresh workspace");
            await updateWorkspaceIfNeeded(cLevelWorkDir, hwid, labid);
        }
        
        log(`Automatically closing files opened from other projects ${activeEditor} ${workdirExists}`)
        if (activeEditor && workdirExists) {
            found = await processTabs(baseCSEPath, cLevelWorkDir);
        }
                
        // Open main.c/.cpp/.rkt/.pl if exists
        // Check if readme.html is currently open in any editor
        const readmeOpen = vscode.window.visibleTextEditors.some(editor => 
            editor.document.fileName.endsWith('readme.html')
        );
        
        console.log("init check to open files", !activeEditor, "found=", found, vscode.workspace.textDocuments.length == 0, "readme open=", readmeOpen);
        log(`init check to open files ${!activeEditor}, ${found}, ${vscode.workspace.textDocuments.length == 0}, readme=${readmeOpen}`);

        // Don't auto-open if readme.html is already open
        if (!readmeOpen && (!activeEditor || found || vscode.workspace.textDocuments.length == 0)) {
            if (initialFiles){
                let firstFileToOpen = true; 
                for (const file of initialFiles) {
                    const filePath = `${cLevelWorkDir}/${file}`;
                    console.log("opening", filePath);

                    if (fsa.existsSync(filePath)) {
                        const fileUri = vscode.Uri.file(filePath);
                        if (await vscode.workspace.fs.stat(vscode.Uri.file(filePath))) {
                            if (firstFileToOpen){
                                await vscode.window.showTextDocument(fileUri);
                                firstFileToOpen = false;
                            } else {
                                await vscode.window.showTextDocument(fileUri, {
                                    preview: false,
                                    preserveFocus: true
                                });
                            }
                        } else {
                            console.log(`FILE NOT FOUND BY workspace ${filePath}`)
                        }
                    }

                }            
            } else {
                log('re-opening main document for this workspace');
                const possibleExtensions = ['c', 'cpp', 'rkt', 'pl'];
                for (const ext of possibleExtensions) {
                    const filePath = `${cLevelWorkDir}/main.${ext}`;
                    if (fsa.existsSync(filePath)) {
                        const fileUri = vscode.Uri.file(filePath);
                        vscode.window.showTextDocument(fileUri);
                        break;
                    }
                }            
            }
        }
    }

    // async function startClipboardListener(context){
    //     if (CBReaderInterval !== null){
    //         clearInterval(CBReaderInterval)
    //     }
    //     CBReaderInterval = setInterval(async () => {            
    //         if (clipboardAccessEnabled && clipboardCheckerEnabled){
    //             const isFocused = vscode.window.state.focused;
    //             console.log( "clipboardInervalChecker: ", clipboardAccessEnabled, clipboardCheckerEnabled, isFocused);                
    //             if (isFocused){
    //                 try{
    //                     const currentClipboard = await vscode.env.clipboard.readText();
    //                     //log(`current cp = ${currentClipboard.length}b ${selectionsSet.has(currentClipboard)} \n\t${currentClipboard}\n\t^^^^^^^^^^^^^^\n`);
    //                     if (currentClipboard === "" || currentClipboard.length === 0){
    //                         clipboardCheckerEnabled = false;
    //                         console.log("Auto checker has disabled clipboard checker due to no value returned from clipboard");
    //                         log("Auto checker has disabled clipboard checker due to no value returned from clipboard");
    //                     }
    //                     if (!selectionsSet.has(currentClipboard) && !cliboardTrack.has(currentClipboard) && currentClipboard.length > 100){
    //                         const now = new Date();
    //                         let text =  `*******************************  ${now.toISOString()} ********************************\n`;
    //                         text +=  `${currentClipboard} \n`;
    //                         try {        
    //                             let encoded = Buffer.from(text).toString('base64');
    //                             await fs.appendFile(CB_LOG_PATH, encoded + "\n");
    //                         } catch (error){
    //                             log('There was an error encoding the pasted information\n${text}')                                
    //                         }
    //                         cliboardTrack.add(currentClipboard);
    //                     }
    //                 } catch (error){
    //                     clipboardAccessEnabled = false; 
    //                 }
    //             } 
    //         } else {
    //             console.log("clipboardInervalChecker (disabled): ", clipboardAccessEnabled, clipboardCheckerEnabled);
    //         }
    //     }, 1000 * 30); // Polling every second
    //     context.subscriptions.push({
    //         dispose: () => clearInterval(CBReaderInterval)
    //     });
    // }
        
}


function deactivate() {
    isDeactivating = true;
    const now = new Date();
    fsa.appendFileSync(PWN_STATUS_FILE, `deactivated ${extensionId} at ${now}\n`);

    // Clear intervals
    if (CBReaderInterval !== null) {
        clearInterval(CBReaderInterval);
        CBReaderInterval = null;
    }
    
    // Stop session monitoring
    if (sessionCheckInterval !== null) {
        clearInterval(sessionCheckInterval);
        sessionCheckInterval = null;
        logSync('Stopped session monitoring interval');
    }

    // Clear timeout
    if (debounceTimeout) {
        clearTimeout(debounceTimeout);
    }
    
   
    logSync(`Detected deactivation event in pwn extension at ${now.toISOString()} `)
            

//     const bashrcPath = path.join('/home/hacker', '.bashrc');
//     const marker = "# PWN_MATE_DEACTIVATION_WARNING"; // Unique marker to identify our message
//     try {
//         const bashrcContent = fsa.readFileSync(bashrcPath, { encoding: 'utf-8' });
//         if (!bashrcContent.includes(marker)) {
//             const deactivationDate = new Date().toISOString().slice(0, 10).replace(/-/g, ''); // Format YYYYMMDD
//             const message = `
// ${marker}
// deactivation_date=${deactivationDate}  # Set the date the extension was deactivated 
// current_date=\$(date +%Y%m%d)
// end_date=\$(date -d "\${deactivation_date} + 7 days" +%Y%m%d)

// if [[ \${current_date} -le \${end_date} ]]; then
//     echo "*********************************************************************************************"
//     printf  "\\033[1;91m WARNING! EXTENSION DISABLED\!\\033[0m\n"    
//     echo "We recorded that you disabled the pwn mate extension.  "
//     echo "The extension has been automatically re-enabled. "    
//     printf "Disabling it more than once \\033[1;91m WILL RESULT IN AN AIV.\\033[0m Do not disable the extension again\!\n"
//     echo "This message will continue for one week."
//     echo "*********************************************************************************************"
// fi
// # End of pwn mate warning
// `;
//             fsa.appendFileSync(bashrcPath, message);
//             console.log('Message appended to .bashrc successfully.');
//             logSync('Added .bashrc message successfully')
//         } else {
//             console.log('Deactivation message already present in .bashrc.');
//             logSync('Deactivation message already present in .bashrc.')
//         }
//     } catch (err) {
//         console.error('Error accessing .bashrc:', err);
//         logSync(`Error accessing .bashrc: ${err}`);
//     }
}

/**
 * Load level configuration from /challenge/.config/level.json
 * Populates the global levelConfig object with challenge details
 * @returns {Promise<boolean>} True if config was loaded successfully
 */
async function loadLevelConfig() {
    const configPath = '/challenge/.config/level.json';
    try {
        if (!fsa.existsSync(configPath)) {
            log('Level config not found at ' + configPath);
            return false;
        }
        
        const data = await fs.readFile(configPath, 'utf8');
        const configData = JSON.parse(data);
        
        // Populate global levelConfig object
        levelConfig.hw = configData;
        levelConfig.hwid = configData.hwid;
        levelConfig.labid = configData.labid;
        levelConfig.level = configData.level;
        levelConfig.initialFiles = configData.initial_files;
        levelConfig.isExam = typeof configData.examLevel === "string" && configData.examLevel.length > 4;
        levelConfig.courseCode = configData.course_code || "cse240";
        levelConfig.cLevelWorkDir = `${configData.hwdir}/${configData.level}`;
        levelConfig.module = configData.module;
        levelConfig.challenge = configData.challenge;
        levelConfig.module_name = configData.module_name;
        levelConfig.challenge_name = configData.challenge_name;
        
        log(`Level config loaded: ${levelConfig.challenge_name} (${levelConfig.module_name})`);
        return true;
    } catch (error) {
        log(`Error loading level config: ${error.message}`);
        return false;
    }
}

/**
 * Load session configuration from /.user_info and level.json
 * Determines if this is an exam session and gets pwn_college_id
 */
async function loadSessionConfiguration() {
    try {
        log('[Config] ========== LOADING SESSION CONFIGURATION ==========');
        
        // Read /.user_info to get pwn_college_id
        const userInfoPath = '/.user_info';
        log(`[Config] Checking for user info at: ${userInfoPath}`);
        
        if (fsa.existsSync(userInfoPath)) {
            log('[Config] ✓ User info file found, reading...');
            const userInfo = await fs.readFile(userInfoPath, 'utf8');
            log(`[Config] User info file size: ${userInfo.length} bytes`);
            
            const match = userInfo.match(/pwn_college_id=['"]?(\d+)['"]?/);
            if (match) {
                pwnCollegeId = match[1];
                log(`[Config] ✓ Loaded pwn_college_id: ${pwnCollegeId}`);
            } else {
                log('[Config] ⚠️  Could not find pwn_college_id pattern in /.user_info');
                log(`[Config] File preview: ${userInfo.substring(0, 200)}...`);
            }
        } else {
            log('[Config] ⚠️  /.user_info file not found');
        }
        
        // Read level.json to check if this is an exam session
        const levelJsonPath = '/challenge/.config/level.json';
        log(`[Config] Checking for level config at: ${levelJsonPath}`);
        
        if (fsa.existsSync(levelJsonPath)) {
            log('[Config] ✓ Level config file found, reading...');
            const levelData = JSON.parse(await fs.readFile(levelJsonPath, 'utf8'));
            isExamSession = levelData.examLevel !== undefined && levelData.examLevel !== null;
            log(`[Config] examLevel value: ${levelData.examLevel}`);
            log(`[Config] Is exam session: ${isExamSession}`);
        } else {
            log('[Config] ⚠️  /challenge/.config/level.json not found');
            isExamSession = false;
        }
        
        log('[Config] ========== CONFIGURATION LOADED ==========');
        log(`[Config] Final state - pwn_college_id: ${pwnCollegeId}, isExam: ${isExamSession}`);
        
    } catch (error) {
        log(`[Config] ❌ ERROR loading session configuration: ${error}`);
        log(`[Config] Error stack: ${error.stack}`);
        throw error;
    }
}

/**
 * Check if /challenge/.dead file exists (indicates session should be terminated)
 * @returns {boolean} true if .dead file exists, false otherwise
 */
function checkDeadFile() {
    try {
        if (fsa.existsSync('/challenge/.dead')) {
            log('[Session Check] Found /challenge/.dead - session terminated');
            return true;
        }
        return false;
    } catch (error) {
        log(`[Session Check] ERROR checking for .dead file: ${error}`);
        return false;
    }
}

/**
 * Start monitoring for session termination
 */
function startSessionMonitoring(context) {
    log('[Session Monitor] Starting session monitoring...');
    log(`[Session Monitor] Check interval: ${SESSION_CHECK_INTERVAL_MS / 1000} seconds`);
    log(`[Session Monitor] Monitoring for /challenge/.dead file`);
    
    // Check immediately on startup
    performSessionCheck();
    
    // Then check every 10 seconds
    sessionCheckInterval = setInterval(() => {
        performSessionCheck();
    }, SESSION_CHECK_INTERVAL_MS);
    
    // Add to context subscriptions for cleanup
    context.subscriptions.push({
        dispose: () => {
            if (sessionCheckInterval) {
                clearInterval(sessionCheckInterval);
                sessionCheckInterval = null;
            }
        }
    });
}

/**
 * Perform session check: check if /challenge/.dead file exists
 */
function performSessionCheck() {
    // Check if the .dead file exists
    const isDead = checkDeadFile();
    
    if (isDead) {
        clearTabsAndShowMessage();
    }
}



/**
 * Clear all open tabs and exit VS Code
 */
async function clearTabsAndShowMessage() {
    try {
        log('[Session Check] Session ended - closing all tabs and shutting down...');
        
        // Close all tabs without saving
        const allTabGroups = vscode.window.tabGroups.all;
        for (const group of allTabGroups) {
            for (const tab of group.tabs) {
                try {
                    await vscode.window.tabGroups.close(tab, true);
                } catch (error) {
                    log(`[Session Check] Error closing tab: ${error}`);
                }
            }
        }
        
        // Create /tmp/done directory and message.md file
        const message = "# Exam Session Ended\n\n" +
                        "You have left the exam and the code is no longer available using the exam session.\n\n" +
                        "To review your exam code, please open Chrome and start a new instance of the Sandbox.\n\n" +
                        "**Example:** To view files for exam 3 (aka exam30) problem 04:\n\n" + 
                        "1. Open the Sandbox module\n" +
                        "2. In the terminal, type: `code ~/cse240/exam30/04/`\n\n" +
                        "This window will close automatically.\n"; 
        
        const doneDir = '/tmp/done';
        const messageFile = '/tmp/done/message.md';
        
        // Create directory if it doesn't exist
        if (!fsa.existsSync(doneDir)) {
            await fs.mkdir(doneDir, { recursive: true });
        }
        
        // Write message to file
        await fs.writeFile(messageFile, message);
        log('[Session Check] Created /tmp/done/message.md');
        
        // // Change workspace to /tmp/done
        // await vscode.workspace.updateWorkspaceFolders(0, 
        //     vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders.length : 0,
        //     { uri: vscode.Uri.file(doneDir) }
        // );
        // log('[Session Check] Changed workspace to /tmp/done');
        
        // Open the message file
        const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(messageFile));
        await vscode.window.showTextDocument(doc, {
            preview: false,
            preserveFocus: false
        });
        log('[Session Check] Opened message.md');
        
        // Show notification
        vscode.window.showWarningMessage('Exam session ended. All files closed.');
        log('[Session Check] Displayed message');
        
        // Create /tmp/.killme file as signal for session_monitor
        try {
            const killmeFile = '/tmp/.killme';
            const timestamp = new Date().toISOString();
            await fs.writeFile(killmeFile, `Session ended at ${timestamp}\n`);
            log('[Session Check] Created /tmp/.killme file');
        } catch (error) {
            log(`[Session Check] Failed to create /tmp/.killme: ${error}`);
        }
        
    } catch (error) {
        log(`[Session Check] ERROR during shutdown: ${error}`);
        // Force quit even if there's an error
        try {
            await vscode.commands.executeCommand('workbench.action.quit');
        } catch (e) {
            // Final fallback
        }
    }
}

module.exports = {
    activate,
    deactivate
};


/**
 * Utility functions 
 */

async function getSortedDirectoriesByModified(historyBasePath) {
    const directories = await fs.readdir(historyBasePath, { withFileTypes: true });

    // Filter to include only directories
    const dirPromises = directories
        .filter(dirent => dirent.isDirectory())
        .map(async dirent => {
            const fullPath = path.join(historyBasePath, dirent.name);
            const stats = await fs.stat(fullPath);
            return { name: dirent.name, mtime: stats.mtime.getTime(), fullPath };
        });

    // Wait for all promises to resolve and sort by modification time (descending)
    const dirInfo = await Promise.all(dirPromises);
    dirInfo.sort((a, b) => b.mtime - a.mtime);

    return dirInfo.map(dir => dir.fullPath);
}

async function findHistoryDirectory(filePath) {

    //filePath="25-proj-mud/01/main.c"

    if (historyMap.has(filePath)) {
        return historyMap.get(filePath);
    }

    try {
        const directories = await getSortedDirectoriesByModified(historyBasePath);
        for (const dirPath of directories) {
            const entriesPath = path.join(dirPath, 'entries.json');
            if (await fs.stat(entriesPath).then(stat => stat.isFile()).catch(() => false)) {
                const entries = JSON.parse(await fs.readFile(entriesPath, 'utf-8'));
                const resource = entries["resource"];

                if (resource.endsWith(filePath)) {
                    historyMap.set(filePath, dirPath);
                    return dirPath;
                }
            }
        }

    } catch (err) {
        vscode.window.showInformationMessage(`error finding ${filePath}`);
        log(`Error finding history directory for ${filePath}: ${err}`); // Log errors
    }

    console.log("Using default history base path."); // Log when using the default path
    //vscode.window.showInformationMessage(`Using /tmp to store pasted info`);
    return "/home/hacker/.local/share/ultima/skipped";
}
