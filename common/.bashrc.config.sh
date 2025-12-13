
if [[ -f /challenge/errorlog ]]; then 
    cat /challenge/errorlog
fi 

if [ -e /challenge/model ] || [ -e /challenge/.init ]; then 
    printf "\n\033[33mWARN: either /challenge/model or /challenge/.init is available\033[0m\n"
fi 

export clevel_work_dir=$(jq -r '. | "\(.hwdir)/\(.level)"' /challenge/.config/level.json)

# if template does not contain student test skeletons then log it and re-add
if grep -q "requiredUserTests"  '/challenge/.config/level.json'; then 
    jq -r '.requiredUserTests[]' /challenge/.config/level.json | while read -r ut_path; do
        ut_path=${ut_path//<hwdir>/$clevel_work_dir}
        if [[ $ut_path == /home/user_tests* ]]; then
            continue
        fi
        if [ ! -d $(dirname $ut_path) ]; then 
            mkdir -p $(dirname $ut_path)        
        fi     
        if [ ! -f $ut_path ]; then  
            printf "\033[33mUser test is missing ($ut_path). Adding $ut_path from /challenge/template/user_tests/$(basename $ut_path) \n\033[0m"  
            cp /challenge/template/user_tests/$(basename $ut_path) $ut_path
        fi     
    done 
else
    # echo "[+] Skipping requiredUserTest copy because not used for this level" 
    # do nothing
    true 
fi 

function save_compile(){
    local compiler="$1"
    local command="$2"
    local result="$3"
    local hw_id=$(jq -r 'if .hw == null then "" else .hw end' /challenge/.config/level.json)
    local module=$(jq -r 'if .module == null or .module == "" then .hw else .module end' /challenge/.config/level.json)
    local lab_id=$(jq -r 'if .labid == null then "" else .labid end' /challenge/.config/level.json)
    local level_id=$(jq -r 'if .level == null then "" else .level end' /challenge/.config/level.json)
    local clevel_work_dir=$(jq -r '. | "\(.hwdir)/\(.level)"' /challenge/.config/level.json)
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local outcome_text=$(cat "$clevel_work_dir/compile.log" | sed "s/'/''/g")

    sqlite3 /home/hacker/cse240/.vscode/trdb.db <<EOF
    CREATE TABLE IF NOT EXISTS compilations (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        module TEXT,
        hw_id TEXT,
        level_id TEXT,
        lab_id TEXT,
        clevel_work_dir TEXT,
        compiler TEXT,
        command TEXT,
        outcome TEXT,
        result TEXT
    );    
    INSERT INTO compilations (timestamp, module, hw_id, level_id, lab_id, clevel_work_dir, compiler, command, outcome, result) VALUES (
        '$timestamp',
        '$module',
        '$hw_id',
        '$level_id',
        '$lab_id',
        '$clevel_work_dir',
        '$compiler',
        '$command',
        '$outcome_text',
        '$result'
    );    
    
EOF
}


export hw_id=$(jq -r '. | "\(.hw)"' /challenge/.config/level.json)
export lab_id=$(jq -r '. | "\(.labid)"' /challenge/.config/level.json)
export level_id=$(jq -r '. | "\(.level)"' /challenge/.config/level.json)
if [[ $hw_id == "null" ]]; then 
    export prompt_info="Lab-$lab_id-$level_id"
else
    export prompt_info="Proj-$hw_id-$level_id"
fi 
export CSE240_PS1="\[\033[38;5;172m\]\u@$prompt_info:\[\033[38;5;36m\] \w\[\033[38;5;172m\] \$ \[\033[00m\]"

# echo "clevel_work_dir=$clevel_work_dir"

if [ -d $clevel_work_dir ]; then 
    clevel_work_dir=$(realpath $clevel_work_dir)

    hw_id=$(jq -r '.hw' /challenge/.config/level.json)
    # Use only the alias for gcc to avoid function/alias conflicts and syntax errors
    gcc() {
        rm -f main.bi*.gc??        
        command gcc -O0 -g -fdiagnostics-color=always -Wall -Werror -ftest-coverage -fprofile-arcs "$@" 2>&1 | tee "$clevel_work_dir/compile.log"
        local rc=${PIPESTATUS[0]}
        if [ "$rc" -eq 0 ]; then
            printf "\033[32mCompilation successful!\033[0m\n" > "$clevel_work_dir/compile.log"
        fi
        save_compile "gcc" "gcc -O0 -g -fdiagnostics-color=always -Wall -Werror -ftest-coverage -fprofile-arcs $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
        return $rc
    }

    g++() {
        rm -f main.bi*.gc??
        command g++ -O0 -g -fdiagnostics-color=always -Wall -Werror -ftest-coverage -fprofile-arcs "$@" 2>&1 | tee "$clevel_work_dir/compile.log"
        local rc=${PIPESTATUS[0]}
        if [ "$rc" -eq 0 ]; then
            printf "\033[32mCompilation successful!\033[0m\n" > "$clevel_work_dir/compile.log"
        fi
        save_compile "g++" "g++ -O0 -g -fdiagnostics-color=always -Wall -Werror -ftest-coverage -fprofile-arcs $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
        return $rc
    }
    make() {
        # Use script with -e to preserve exit code and -q for quiet (no headers)
        # The -c flag runs the command and captures both stdout and stderr with TTY emulation
        # Output is shown to user AND saved to compile.log with colors preserved
        script -q -e -c "make $*" "$clevel_work_dir/compile.log"
        local rc=$?
        if [ "$rc" -eq 0 ]; then
            printf "\033[32mCompilation successful!\033[0m\n" > "$clevel_work_dir/compile.log"
        fi
        # Try to detect compiler from Makefile
        local detected_compiler="make"
        if [ -f "Makefile" ]; then
            # Extract object files from OBJS variable if it exists
            local objs=$(grep -oP '^\s*OBJS\s*[?:+]?=\s*\K.*' Makefile | tr '\n' ' ')
            local detected_files=""
            if [ -n "$objs" ]; then
                # Convert .o files to .c/.cpp files
                detected_files=$(echo "$objs" | sed 's/\.o/\.c/g; s/\.o/\.cpp/g')
            fi
            
            if grep -q "^\s*CC\s*=\s*gcc" Makefile || grep -q "gcc" Makefile; then
                detected_compiler="make(gcc)"
            elif grep -q "^\s*CC\s*=\s*g++" Makefile || grep -q "^\s*CXX\s*=\s*g++" Makefile || grep -q "g++" Makefile; then
                detected_compiler="make(g++)"
            fi
            
            # Update the make command in save_compile call to include detected files
            local make_command="make $*"
            if [ -n "$detected_files" ]; then
                make_command="make $* (objects: $detected_files)"
            fi
            save_compile "$detected_compiler" "$make_command" "$rc" >> /tmp/save_compile.log 2>&1 || true
            return $rc
        fi
        save_compile "$detected_compiler" "make $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
        return $rc
    }
    tester() {
        echo "" >> "$clevel_work_dir/tester.log"
        echo "========================================" >> "$clevel_work_dir/tester.log"
        echo "Test run: $(date '+%Y-%m-%d %H:%M:%S')" >> "$clevel_work_dir/tester.log"
        echo "========================================" >> "$clevel_work_dir/tester.log"
        echo "" >> "$clevel_work_dir/tester.log"
        command tester "$@" 2>&1 | tee -a "$clevel_work_dir/tester.log"
    }

    alias bat='/usr/bin/batcat --pager=never'
    alias reset_mainc='cdhw && cp /challenge/template/main.c ./'
    alias reset_usertests='cdhw && cp /challenge/template/user_tests/* ./user_tests/'
    alias killbins='pkill -f main.bin'
    
    
    # export GCOV_PREFIX=$clevel_work_dir/.test
    # export GCOV_PREFIX_STRIP=$(echo "${clevel_work_dir%?}" | grep -o '/' | wc -l)
    
    ENVFILE=~/cse240/.cse240env
    # tweaks for modified admin testing environment 
    
    alias cdhw="cd $clevel_work_dir"
    if printenv VSCODE_PROXY_URI > /dev/null; then # && ! grep -q "$clevel_work_dir" $ENVFILE ; then 
        alias reset_vs="code-server -r /home/hacker/cse240"
        alias ohw="cd $clevel_work_dir && code-server $clevel_work_dir/main.c"
        LOADFILE=""
        if [ -f $clevel_work_dir/main.c ]; then 
            LOADFILE=$clevel_work_dir/main.c
        elif [ -f $clevel_work_dir/main.cpp ]; then 
            LOADFILE=$clevel_work_dir/main.cpp
        elif [ -f $clevel_work_dir/main.rkt ]; then 
            LOADFILE=$clevel_work_dir/main.rkt
        elif [ -f $clevel_work_dir/main.pl ]; then 
            LOADFILE=$clevel_work_dir/main.pl
        fi
        if [[ "$clevel_work_dir" != *cse240/exam* ]] && [[ "$clevel_work_dir" != *cse240/pretest* ]]; then
            if grep -q '^LAST_LOADED_DIR=' "$ENVFILE"; then
                sed -i 's#^LAST_LOADED_DIR=.*#LAST_LOADED_DIR='$clevel_work_dir'#' "$ENVFILE"
            else
                echo 'LAST_LOADED_DIR='$clevel_work_dir >> "$ENVFILE"
            fi
        fi 
    else # we are sshing
        if [ -d /home/me ]; then 
            echo "ALLOWING ssh access in asuser mode"
            cd $clevel_work_dir
        elif  grep -q YOUVE_GOT_SHELL "$ENVFILE" || grep -q "digital god" /.admin_access; then
            echo "ALLOWING ssh access with bypass enabled"
            cd $clevel_work_dir
        else
            if grep -q -E "129884|128254|37215" /.user_info; then
                echo "ALLOWING ssh access with bypass enabled for 129884, 128254, and 37215"
                cd $clevel_work_dir
            else
                echo "You do not have access to the shell in this mode. Please use the VS Code interface."
                echo "Please use the VS Code interface to work on your code."
                echo "If you need terminal access, please contact your instructor or system administrator."
                echo "DIRECT TERMINAL ACCESS AND THE DESKTOP MODES ARE NOT PERMITTED "
                echo "IF pwn.college defaulted you to this view, click on the word terminal below and select code."
                echo "This will change you into the VS Code view."
                exec true
            fi 
        fi
    fi 
    
fi 

if grep -q "digital god" /.admin_access ; then 
    printf "\n\033[38;5;10mADMIN ACCESS is enabled\033[0m\n"
    alias gr='gcc main.c -o main.bin && ./main.bin'
    alias mtests='sqlite3 ~/cse240/.vscode/trdb.db "select * from tests where module like '\''$hw_id-%'\'' order by timestamp"'
    alias ctests='sqlite3 ~/cse240/.vscode/trdb.db "select * from tests where module like '\''$hw_id-%'\'' and level = $level_id order by timestamp"'
    # alias compilations='sqlite3 ~/cse240/.vscode/trdb.db "select * from compilations where hw_id = '\''$hw_id'\'' and level_id = '\''$level_id'\'' order by timestamp ASC"'
    alias compilations='sqlite3 -line ~/cse240/.vscode/trdb.db "select timestamp, level_id, compiler, result, outcome from compilations where hw_id = '\''$hw_id'\'' and level_id = '\''$level_id'\'' and command not like '\''make clean%'\'' order by timestamp ASC"'
    alias sqlf='sqlite3 -header -column ~/cse240/.vscode/trdb.db'
    alias sql='sqlite3 ~/cse240/.vscode/trdb.db'
    
fi 

alias cpdat='tail -100 ~/cse240/.vscode/cp.dat |xargs -L 1 -I{} bash -c "printf {} | base64 --decode; echo "'
alias cpdatfull='cat ~/cse240/.vscode/cp.dat |xargs -L 1 -I{} bash -c "printf {} | base64 --decode; echo "'
alias cbinfodat='cat ~/cse240/.vscode/cbinfo.dat |xargs -L 1 -I{} bash -c "printf {} | base64 --decode; echo "'
alias heartlog='cat ~/.local/share/ultima/pexs.log '
function diff_size() {
    tr -s '[:space:]' '\n' < "$1" > /tmp/diff_size_file1.tmp
    tr -s '[:space:]' '\n' < "$2" > /tmp/diff_size_file2.tmp
    diff -u /tmp/diff_size_file1.tmp /tmp/diff_size_file2.tmp | grep -E '^[+]' | grep -v '^+++' | grep -v '^---' | wc -c
}
alias batlist='for f in $(ls -tr); do ls -lat $f; batcat --paging=never $f; done'
alias difflist='last="";for f in $(ls -tr ????.c); do ls -lat $f; if [ -n "$last" ]; then printf "\033[38;5;13mThe Difference size between $last and $f is "; diff_size $last $f; printf "\033[0m"; icdiff $last $f; fi; batcat --paging=never $f; last=$f; done'

alias gdb-gef='echo -e "\nsource /opt/gef/gef.py\n" > /home/hacker/.gdbinit'
alias gdb-no-gef='echo -e "\n\n" > /home/hacker/.gdbinit'




if [ -f /challenge/.config/.bashrc.level.sh ]; then 

    source /challenge/.config/.bashrc.level.sh

fi 

if [ -d /home/other/cse240 ] && [ -f /challenge/bin/checker ]; then 
    # if in observation mode then run checker for current student's project/level
    echo "Skipping /bin/checker for now"
    # /challenge/bin/checker 
fi 

# if exam or pretest then add tester alias
if [[ "$clevel_work_dir" == *cse240/exam* ]] || [[ "$clevel_work_dir" == *cse240/pretest* ]]; then
    alias tester="/challenge/bin/exam_tester.sh"    
else 
    if tail -n 10 /home/hacker/.bashrc | grep -qE 'CSE240_PS1' && \
            grep -q -v '# AUTO ADDED BY CSE240' /home/hacker/.bashrc; then
        if [[ "$clevel_work_dir" != *cse240/exam* ]] && [[ "$clevel_work_dir" != *cse240/pretest* ]]; then
            sed  -i '/export[[:space:]]\+PS1[[:space:]]*.[[:space:]]*\$CSE240_PS1/{
    c\
    if [ -n "$CSE240_PS1" ]; then \
        export PS1="$CSE240_PS1"\
    fi \
    # AUTO ADDED BY CSE240
    }' "/home/hacker/.bashrc"

        fi 
    fi
fi 

thispwd=$(pwd)

# if [ "$thispwd" != "$clevel_work_dir" ] && printenv | grep -q "VSCODE_"; then
#     if [ ! -f /tmp/ranonce ] ; then 
#         touch /tmp/ranonce
#         workspace=$(find "$thispwd/.." -type f -name "*.code-workspace" | head -n 1)
#         new_workspace="${workspace%.code-workspace}-${level_id}.code-workspace"

#         cp "$workspace" "$new_workspace"        
#         echo "clevel_work_dir=$clevel_work_dir  thispwd=$thispwd $workspace $new_workspace"  | tee -a /tmp/ranonce      

#         code-server -r $new_workspace
        
#     fi
# fi

# Function to open recent code files in code-server
open_recent_exam_code() {
    local exam_dir="/home/hacker/cse240/exam"
    
    # Check if exam directory exists
    if [ ! -d "$exam_dir" ]; then
        echo "Error: Directory $exam_dir does not exist"
        return 1
    fi
    
    # Find all code files and get the most recent modification time
    local most_recent_file=""
    local most_recent_time=0
    
    # Find the most recently modified file
    while IFS= read -r -d '' file; do
        local file_time=$(stat -c %Y "$file" 2>/dev/null)
        if [ "$file_time" -gt "$most_recent_time" ]; then
            most_recent_time="$file_time"
            most_recent_file="$file"
        fi
    done < <(find "$exam_dir" -type f \( -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.rkt" -o -name "*.pl" \) -print0 2>/dev/null)
    
    if [ -z "$most_recent_file" ]; then
        echo "No code files found in $exam_dir"
        return 1
    fi
    
    # Get the modification date of the most recent file (YYYY-MM-DD format)
    local most_recent_date=$(stat -c %y "$most_recent_file" | cut -d' ' -f1)
    
    echo "Most recent file: $most_recent_file (modified on $most_recent_date)"
    
    # Find all code files modified on the same date
    local files_to_open=()
    while IFS= read -r -d '' file; do
        local file_date=$(stat -c %y "$file" | cut -d' ' -f1)
        if [ "$file_date" = "$most_recent_date" ]; then
            files_to_open+=("$file")
        fi
    done < <(find "$exam_dir" -type f \( -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.rkt" -o -name "*.pl" \) -print0 2>/dev/null)
    
    if [ ${#files_to_open[@]} -eq 0 ]; then
        echo "No files found modified on $most_recent_date"
        return 1
    fi
    
    echo "Opening ${#files_to_open[@]} files modified on $most_recent_date:"
    printf '%s\n' "${files_to_open[@]}"
    
    # Open all files in code-server
    code "${files_to_open[@]}"
}




