const vscode = require('vscode');
const path = require('path');
const fs = require('fs').promises; // Ensure using promises API for asynchronous operations
const fsa = require('fs');
const os = require('os');
const https = require('https');

const version = "1.1";
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

const PWN_STATUS_FILE = "/home/hacker/.local/share/ultima/pexs.dat"
const BASEDIR = "/home/hacker/cse240/.vscode/"
const LOGPATH = `${BASEDIR}cp.dat`
const CB_LOG_PATH = `${BASEDIR}cbinfo.dat`
const DB_PATH = `/home/hacker/cse240/.vscode/trdb.db`

async function log(text) {
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
    initEnvironment();

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
                const levelWorkspacePathHwid = `${cLevelWorkDir}/../level-${hwid}.code-workspace`;
                const levelWorkspacePathLabid = `${cLevelWorkDir}/../level-${labid}.code-workspace`;
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
        statusBarItem.text = `Welcome to pwn.college's CSE240 🦆${version}`;
        statusBarItem.show();

        // Hide the message after 15 seconds
        setTimeout(() => {
            statusBarItem.hide();
            statusBarItem.dispose(); // Clean up the status bar item
        }, 15000);
        
        context.subscriptions.push(statusBarItem);

        //log(`clevelWorkDir=${cLevelWorkDir} ${fsa.existsSync(cLevelWorkDir)} ${activeEditor}`);
        
        // Add any startup logic here
        const configPath = '/challenge/.config/level.json';
        let configData;
        try {
            // Check if the config file exists
            if (fsa.existsSync(configPath)) {
                const data = await fs.readFile(configPath, 'utf8');
                configData = JSON.parse(data);
                //log("config data=" + configData); // Or handle the config object as needed
            }
        } catch (error) {
            console.error('Failed to read or parse level.json:', error);
        }
        const cLevelWorkDir = `${configData["hwdir"]}/${configData["level"]}`;
        const hw = configData;
        const hwid = configData["hwid"];
        const labid = configData["labid"];
        const level = configData["level"];
        const initialFiles = configData["initial_files"]
        const activeEditor = vscode.window.activeTextEditor;
        const isExam = typeof configData["examLevel"] === "string" && configData["examLevel"].length > 4;

        if (isExam){
            historyBasePath = path.join(os.homedir(), '.local', 'share', 'code-server-exam', 'User', 'History');
        }

        // Editor: close files from other projects and open files for this project
        // TODO: add fields to /challenge/.config/level.json that tells this process which files to open up
        const baseCSE240Path = "/home/hacker/cse240/";
        var found = false;

        let workdirExists = fsa.existsSync(cLevelWorkDir);
        
        if (workdirExists ){ // if workdir does not esxist may get stuck in infinte reloading loop
            console.log("Checking if we need to refresh workspace");
            await updateWorkspaceIfNeeded(cLevelWorkDir, hwid, labid);
        }
        
        log(`Automatically closing files opened from other projects ${activeEditor} ${workdirExists}`)
        if (activeEditor && workdirExists) {
            found = await processTabs(baseCSE240Path, cLevelWorkDir);
        }
                
        // Open main.c/.cpp/.rkt/.pl if exists
        console.log("init check to open files", !activeEditor, "found=", found, vscode.workspace.textDocuments.length == 0);
        log(`init check to open files ${!activeEditor}, ${found}, ${vscode.workspace.textDocuments.length == 0}`);

        if (!activeEditor || found || vscode.workspace.textDocuments.length == 0) {
            if (initialFiles){
                let firstFileToOpen = false; 
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

    //filePath="05-mud/01/main.c"

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
