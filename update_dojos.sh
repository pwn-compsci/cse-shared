#!/usr/bin/env bash
 
# List of update scripts
scripts=(
  "/cse/intro-to-programming-languages/update_dojo.sh"
  "/cse/cse240-fc25/update_dojo.sh"
  # Add more paths here as needed
)

# Change to the directory of this script
cd "$(dirname "$0")" || exit 1

# Git add, commit, and push
git add .
git commit -m "Update dojo scripts"
git push

declare -A pids
declare -A statuses

# Start all scripts in parallel
for script in "${scripts[@]}"; do
  echo "🔄 Running: $script"
  "$script" &
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
