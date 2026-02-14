
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
    
    # Helper function to trim compile.log if it exceeds 100KB
    trim_compile_log() {
        local log_file="$clevel_work_dir/compile.log"
        if [ -f "$log_file" ]; then
            local file_size=$(stat -c%s "$log_file" 2>/dev/null || stat -f%z "$log_file" 2>/dev/null)
            if [ "$file_size" -gt 102400 ]; then
                # Keep last 80KB to have buffer before next limit
                tail -c 81920 "$log_file" > "$log_file.tmp"
                mv "$log_file.tmp" "$log_file"
            fi
        fi
    }
    
    # Use only the alias for gcc to avoid function/alias conflicts and syntax errors
    gcc() {
        rm -f main.bi*.gc??
        
        # Check level.json for compilation flags
        local limited_gcc_flags=$(jq -r 'if .limited_gcc_flags == true then "true" else "false" end' /challenge/.config/level.json 2>/dev/null || echo "false")
        local codecoverage=$(jq -r 'if .codecoverage then .codecoverage else 0 end' /challenge/.config/level.json 2>/dev/null || echo "0")
        
        # Build flags
        local base_flags="-O0 -g -fdiagnostics-color=always"
        local strict_flags=""
        local profile_flags=""
        
        if [ "$limited_gcc_flags" != "true" ]; then
            strict_flags="-Wall -Werror"
        fi
        
        if [ "$codecoverage" -gt 0 ]; then
            profile_flags="--coverage"
        fi
        
        local all_flags="$base_flags $strict_flags $profile_flags"
        
        # Log original command
        echo "" >> "$clevel_work_dir/compile.log"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Original: gcc $*" >> "$clevel_work_dir/compile.log"
        
        # If code coverage is enabled, check if we need to split compile and link
        if [ "$codecoverage" -gt 0 ]; then
            # Check if this is a compile+link operation (has .c files and -o without -c flag)
            local has_source=false
            local has_output=false
            local has_compile_only=false
            
            for arg in "$@"; do
                if [[ "$arg" == *.c ]]; then
                    has_source=true
                elif [[ "$arg" == "-c" ]]; then
                    has_compile_only=true
                elif [[ "$arg" == "-o" ]]; then
                    has_output=true
                fi
            done
            
            # If compile+link step (source files + output, but not -c flag), split it
            if [ "$has_source" = true ] && [ "$has_output" = true ] && [ "$has_compile_only" = false ]; then
                echo "Code coverage enabled: splitting into compile and link steps" >> "$clevel_work_dir/compile.log"
                
                # Extract source files and other arguments
                local source_files=()
                local other_args=()
                local output_file=""
                local next_is_output=false
                
                for arg in "$@"; do
                    if [ "$next_is_output" = true ]; then
                        output_file="$arg"
                        next_is_output=false
                    elif [[ "$arg" == *.c ]]; then
                        source_files+=("$arg")
                    elif [[ "$arg" == "-o" ]]; then
                        next_is_output=true
                    else
                        other_args+=("$arg")
                    fi
                done
                
                # Derive object file name from output file (e.g., main.bin -> main.o)
                local base_name="${output_file%.*}"
                local object_file="${base_name}.o"
                
                # Step 1: Compile all source files into a single object file
                echo "Step 1: gcc $all_flags -c ${source_files[*]} -o $object_file" >> "$clevel_work_dir/compile.log"
                command gcc $all_flags -c "${source_files[@]}" -o "$object_file" 2>&1 | tee -a "$clevel_work_dir/compile.log"
                local compile_rc=${PIPESTATUS[0]}
                if [ "$compile_rc" -ne 0 ]; then
                    save_compile "gcc" "gcc $all_flags -c ${source_files[*]} -o $object_file" "$compile_rc" >> /tmp/save_compile.log 2>&1 || true
                    trim_compile_log
                    return $compile_rc
                fi
                
                # Step 2: Link object file
                echo "Step 2: gcc $all_flags $object_file ${other_args[*]} -o $output_file" >> "$clevel_work_dir/compile.log"
                command gcc $all_flags "$object_file" "${other_args[@]}" -o "$output_file" 2>&1 | tee -a "$clevel_work_dir/compile.log"
                local rc=${PIPESTATUS[0]}
                if [ "$rc" -eq 0 ]; then
                    printf "\033[32mCompilation successful!\033[0m\n" >> "$clevel_work_dir/compile.log"
                fi
                save_compile "gcc" "gcc $all_flags $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
                trim_compile_log
                return $rc
            fi
        fi
        
        # Normal single-step compilation
        echo "Final:    gcc $all_flags $*" >> "$clevel_work_dir/compile.log"
        command gcc $all_flags "$@" 2>&1 | tee -a "$clevel_work_dir/compile.log"
        local rc=${PIPESTATUS[0]}
        if [ "$rc" -eq 0 ]; then
            printf "\033[32mCompilation successful!\033[0m\n" >> "$clevel_work_dir/compile.log"
        fi
        save_compile "gcc" "gcc $all_flags $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
        trim_compile_log
        return $rc
    }

    g++() {
        rm -f main.bi*.gc??
        
        # Check level.json for compilation flags
        local limited_gcc_flags=$(jq -r 'if .limited_gcc_flags == true then "true" else "false" end' /challenge/.config/level.json 2>/dev/null || echo "false")
        local codecoverage=$(jq -r 'if .codecoverage then .codecoverage else 0 end' /challenge/.config/level.json 2>/dev/null || echo "0")
        
        # Build flags
        local base_flags="-O0 -g -fdiagnostics-color=always"
        local strict_flags=""
        local profile_flags=""
        
        if [ "$limited_gcc_flags" != "true" ]; then
            strict_flags="-Wall -Werror"
        fi
        
        if [ "$codecoverage" -gt 0 ]; then
            profile_flags="--coverage"
        fi
        
        local all_flags="$base_flags $strict_flags $profile_flags"
        
        # Log original command
        echo "" >> "$clevel_work_dir/compile.log"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Original: g++ $*" >> "$clevel_work_dir/compile.log"
        
        # If code coverage is enabled, check if we need to split compile and link
        if [ "$codecoverage" -gt 0 ]; then
            # Check if this is a compile+link operation (has .cpp files and -o without -c flag)
            local has_source=false
            local has_output=false
            local has_compile_only=false
            
            for arg in "$@"; do
                if [[ "$arg" == *.cpp ]] || [[ "$arg" == *.cc ]] || [[ "$arg" == *.cxx ]]; then
                    has_source=true
                elif [[ "$arg" == "-c" ]]; then
                    has_compile_only=true
                elif [[ "$arg" == "-o" ]]; then
                    has_output=true
                fi
            done
            
            # If compile+link step (source files + output, but not -c flag), split it
            if [ "$has_source" = true ] && [ "$has_output" = true ] && [ "$has_compile_only" = false ]; then
                echo "Code coverage enabled: splitting into compile and link steps" >> "$clevel_work_dir/compile.log"
                
                # Extract source files and other arguments
                local source_files=()
                local other_args=()
                local output_file=""
                local next_is_output=false
                
                for arg in "$@"; do
                    if [ "$next_is_output" = true ]; then
                        output_file="$arg"
                        next_is_output=false
                    elif [[ "$arg" == *.cpp ]] || [[ "$arg" == *.cc ]] || [[ "$arg" == *.cxx ]]; then
                        source_files+=("$arg")
                    elif [[ "$arg" == "-o" ]]; then
                        next_is_output=true
                    else
                        other_args+=("$arg")
                    fi
                done
                
                # Derive object file name from output file (e.g., main.bin -> main.o)
                local base_name="${output_file%.*}"
                local object_file="${base_name}.o"
                
                # Step 1: Compile all source files into a single object file
                echo "Step 1: g++ $all_flags -c ${source_files[*]} -o $object_file" >> "$clevel_work_dir/compile.log"
                command g++ $all_flags -c "${source_files[@]}" -o "$object_file" 2>&1 | tee -a "$clevel_work_dir/compile.log"
                local compile_rc=${PIPESTATUS[0]}
                if [ "$compile_rc" -ne 0 ]; then
                    save_compile "g++" "g++ $all_flags -c ${source_files[*]} -o $object_file" "$compile_rc" >> /tmp/save_compile.log 2>&1 || true
                    trim_compile_log
                    return $compile_rc
                fi
                
                # Step 2: Link object file
                echo "Step 2: g++ $all_flags $object_file ${other_args[*]} -o $output_file" >> "$clevel_work_dir/compile.log"
                command g++ $all_flags "$object_file" "${other_args[@]}" -o "$output_file" 2>&1 | tee -a "$clevel_work_dir/compile.log"
                local rc=${PIPESTATUS[0]}
                if [ "$rc" -eq 0 ]; then
                    printf "\033[32mCompilation successful!\033[0m\n" >> "$clevel_work_dir/compile.log"
                fi
                save_compile "g++" "g++ $all_flags $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
                trim_compile_log
                return $rc
            fi
        fi
        
        # Normal single-step compilation
        echo "Final:    g++ $all_flags $*" >> "$clevel_work_dir/compile.log"
        command g++ $all_flags "$@" 2>&1 | tee -a "$clevel_work_dir/compile.log"
        local rc=${PIPESTATUS[0]}
        if [ "$rc" -eq 0 ]; then
            printf "\033[32mCompilation successful!\033[0m\n" >> "$clevel_work_dir/compile.log"
        fi
        save_compile "g++" "g++ $all_flags $*" "$rc" >> /tmp/save_compile.log 2>&1 || true
        trim_compile_log
        return $rc
    }
    make() {
        # Log make command with timestamp (append mode)
        echo "" >> "$clevel_work_dir/compile.log"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running: make $*" >> "$clevel_work_dir/compile.log"
        
        # Check level.json for compilation flags
        local limited_gcc_flags=$(jq -r 'if .limited_gcc_flags == true then "true" else "false" end' /challenge/.config/level.json 2>/dev/null || echo "false")
        local codecoverage=$(jq -r 'if .codecoverage then .codecoverage else 0 end' /challenge/.config/level.json 2>/dev/null || echo "0")
        
        # Build flags for make
        local base_flags="-O0 -g -fdiagnostics-color=always"
        local strict_flags=""
        local coverage_flags=""
        
        if [ "$limited_gcc_flags" != "true" ]; then
            strict_flags="-Wall -Werror"
        fi
        
        if [ "$codecoverage" -gt 0 ]; then
            coverage_flags="--coverage"
            echo "Code coverage enabled for make" >> "$clevel_work_dir/compile.log"
        fi
        
        local all_flags="$base_flags $strict_flags $coverage_flags"
        
        # Try to detect compiler and files from Makefile
        local detected_compiler="make"
        local detected_files=""
        if [ -f "Makefile" ]; then
            # Extract object files from OBJS variable if it exists
            local objs=$(grep -oP '^\s*OBJS\s*[?:+]?=\s*\K.*' Makefile | tr '\n' ' ')
            if [ -n "$objs" ]; then
                # Convert .o files to .c/.cpp files
                detected_files=$(echo "$objs" | sed 's/\.o/\.c/g; s/\.o/\.cpp/g')
            fi
            
            # Detect compiler type
            if grep -q "^\s*CC\s*=\s*gcc" Makefile || grep -q "gcc" Makefile; then
                detected_compiler="make(gcc)"
            elif grep -q "^\s*CC\s*=\s*g++" Makefile || grep -q "^\s*CXX\s*=\s*g++" Makefile || grep -q "g++" Makefile; then
                detected_compiler="make(g++)"
            fi
            
            # Log detected files to compile.log
            if [ -n "$detected_files" ]; then
                echo "Detected files: $detected_files" >> "$clevel_work_dir/compile.log"
            fi
        fi
        
        # If coverage is enabled, pass flags via environment variables
        if [ "$codecoverage" -gt 0 ]; then
            echo "Running make with CFLAGS=\"$all_flags\" CXXFLAGS=\"$all_flags\"" >> "$clevel_work_dir/compile.log"
            CFLAGS="$all_flags" CXXFLAGS="$all_flags" command make "$@" 2>&1 | tee -a "$clevel_work_dir/compile.log"
        else
            # Run make normally
            command make "$@" 2>&1 | tee -a "$clevel_work_dir/compile.log"
        fi
        local rc=${PIPESTATUS[0]}
        
        if [ "$rc" -eq 0 ]; then
            printf "\033[32mCompilation successful!\033[0m\n" >> "$clevel_work_dir/compile.log"
        fi
        
        # Update the make command in save_compile call to include detected files
        local make_command="make $*"
        if [ -n "$detected_files" ]; then
            make_command="make $* (objects: $detected_files)"
        fi
        save_compile "$detected_compiler" "$make_command" "$rc" >> /tmp/save_compile.log 2>&1 || true        trim_compile_log        return $rc
    }
    tester() {
        command tester "$@" 2>&1 | tee "$clevel_work_dir/tester.log"
        echo "" >> "$clevel_work_dir/.tester_hist.log"
        echo "========================================" >> "$clevel_work_dir/.tester_hist.log"
        echo "Test run: $(date '+%Y-%m-%d %H:%M:%S')" >> "$clevel_work_dir/.tester_hist.log"
        echo "========================================" >> "$clevel_work_dir/.tester_hist.log"
        echo "" >> "$clevel_work_dir/.tester_hist.log"
        cat "$clevel_work_dir/tester.log" >> "$clevel_work_dir/.tester_hist.log"
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
if [[ "$clevel_work_dir" == *cse240/exam* ]] || [[ "$clevel_work_dir" == *cse240/pretest* ]] || [[ "$clevel_work_dir" == *cse240/pex* ]]; then
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




