#!/usr/bin/env bash
 
# List of update scripts
scripts=(
  "/cse/intro-to-programming-languages/update_dojo.sh"
  "/cse/cse240-fa26/update_dojo.sh"
  "/cse/cse240-fc26/update_dojo.sh"
  # Add more paths here as needed
)

# Change to the directory of this script
cd "$(dirname "$0")" || exit 1

run_as=()
if [[ "$(id -un)" == "etrickel" ]]; then
  run_as=(sudo -H -u duck --)
  echo "Logged in as etrickel; running dojo update commands as duck."
fi

# Git add, commit, and push
"${run_as[@]}" git add .
"${run_as[@]}" git commit -m "Update dojo scripts"
"${run_as[@]}" git push

declare -A pids
declare -A statuses 

# Start all scripts in parallel
for script in "${scripts[@]}"; do
  "${run_as[@]}" touch "$script"  # Ensure the script exists
  echo "🔄 Running: $script"
  "${run_as[@]}" "$script" &
  pids["$script"]=$!
done

# Wait for all and record statuses
for script in "${scripts[@]}"; do
  wait "${pids[$script]}"
  statuses["$script"]=$?
done

# Check results
all_success=true
for script in "${scripts[@]}"; do
  if [[ ${statuses[$script]} -eq 0 ]]; then
    echo "✅ $script completed successfully."
  else
    echo "❌ $script failed with exit code ${statuses[$script]}."
    all_success=false
  fi
done

# Final status
if $all_success; then
  echo "🎉 All runs completed successfully."
  exit 0
else
  echo "⚠️ One or more runs failed."
  exit 1
fi
