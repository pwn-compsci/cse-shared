
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

    alias gcc="rm -f main.bi*.gc??; gcc -O0 -g -fdiagnostics-color=always -Wall -Werror  -ftest-coverage -fprofile-arcs "
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
        if [[ "$clevel_work_dir" != *cse240/exam* ]]; then
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
            echo "DIRECT SSH ACCESS IS NOT PERMITTED BUT IS ENABLED"
            # TODO: REENABLE THIS 
            #exec true
        fi
    fi 
    
fi 

if grep -q "digital god" /.admin_access ; then 
    printf "\n\033[38;5;10mADMIN ACCESS is enabled\033[0m\n"
    alias gr='gcc main.c -o main.bin && ./main.bin'
    alias mtests='sqlite3 ~/cse240/.vscode/trdb.db "select * from tests where module like '\''$hw_id-%'\'' order by timestamp"'
    alias ctests='sqlite3 ~/cse240/.vscode/trdb.db "select * from tests where module like '\''$hw_id-%'\'' and level = $level_id order by timestamp"'
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

if tail -n 10 /home/hacker/.bashrc | grep -qE 'CSE240_PS1' && \
        grep -q -v '# AUTO ADDED BY CSE240' /home/hacker/.bashrc; then
    if [[ "$clevel_work_dir" != *cse240/exam* ]]; then
        sed  -i '/export[[:space:]]\+PS1[[:space:]]*.[[:space:]]*\$CSE240_PS1/{
c\
if [ -n "$CSE240_PS1" ]; then \
    export PS1="$CSE240_PS1"\
fi \
# AUTO ADDED BY CSE240
}' "/home/hacker/.bashrc"

    fi 
fi


if [ -f /challenge/.config/.bashrc.level.sh ]; then 

    source /challenge/.config/.bashrc.level.sh

fi 

if [ -d /home/other/cse240 ] && [ -f /challenge/bin/checker ]; then 
    # if in observation mode then run checker for current student's project/level
    echo "Skipping /bin/checker for now"
    # /challenge/bin/checker 
fi 
# if exam 
if [[ "$clevel_work_dir" == *cse240/exam* ]]; then
    alias tester="/challenge/bin/exam_tester.sh"
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




