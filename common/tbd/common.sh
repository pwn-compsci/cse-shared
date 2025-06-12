#! /opt/pwn.college/bash
testcnt=1

# Function to generate a random directory name
generate_random_name() {
    head /dev/urandom | tr -dc A-Za-z0-9 | head -c 8
}

log_pos() {
    msg="$1"
    printf "\t${testcnt}. \033[38;5;10m✔ ️$msg\033[0m\n"
    testcnt=$(( testcnt + 1 ))
}
log_neg() {
    msg="$1"
    printf "\n\033[38;5;9m$msg\033[0m\n"
}

log_and_exec(){
    ## print the command to the logfile
    printf "\033[38;5;8m%s\033[0m\n" "$@"
    ## run the command and redirect it's error output
    ## to the logfile
    eval "$@"
}

generate_random_face() {
    # Define an array of emoji faces
    faces=("😀" "😁" "😂" "🤣" "😃" "😄" "😅" "😆" "😉" "😊" "😋" "😎" "😍" "😘" "🥰" "😚" "😗" "😙" "😜" "😝" "🤤" "😪" "😫" "😴" "😌" "😛" "😏" "😒" "😞" "😔" "😟" "😖" "😣" "😓" "😭" "😢" "😮" "😲" "😳" "🥺" "😦" "😧" "😨" "😰" "😥" "😓" "🤗" "🤔" "🤭" "🤫" "🤥" "😶" "😐" "😑" "😬" "🙄" "😯" "😴" "😌" "😛" "😜" "😝" "🤤" "😒" "😔" "😪" "🤐" "🤨" "🤓" "😈" "👿" "🤑" "🤠" "😷" "🤧" "🥵" "🥶" "🥴" "😵" "🤯" "🤠" "🥳" "😎" "🤓" "🧐" "😕" "😟" "🙁" "☹" "😮" "😯" "😲" "😳" "🥵" "🥶" "😱" "😨" "😰" "😥" "😓" "🥱" "😴" "😩" "😫" "😤" "😡" "😠" "🤬" "😈" "👿")

    # Get the size of the array
    size=${#faces[@]}

    # Generate a random index
    index=$((RANDOM % size))

    # Print the emoji face at the randomly chosen index
    echo ${faces[$index]}
}