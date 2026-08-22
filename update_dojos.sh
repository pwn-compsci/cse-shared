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
if [[ "$(stat -c %U .)" == "duck" && "$(id -un)" != "duck" ]]; then
  run_as=(sudo -H -u duck --)
  echo "Current directory is owned by duck; running dojo update commands as duck."
fi

# Git add, commit, and push
"${run_as[@]}" git add .
"${run_as[@]}" git commit -m "Update dojo scripts"
"${run_as[@]}" git push
expected_shared_commit=$("${run_as[@]}" git rev-parse HEAD)

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

# Verify each dojo actually picked up the cse-shared commit we just pushed.
for script in "${scripts[@]}"; do
  repo_dir="$(dirname "$script")"
  shared_dir="$repo_dir/cse-shared"

  if [[ ! -d "$shared_dir/.git" && ! -f "$shared_dir/.git" ]]; then
    echo "❌ $repo_dir does not have a cse-shared submodule checkout."
    all_success=false
    continue
  fi

  actual_shared_commit=$("${run_as[@]}" git -C "$shared_dir" rev-parse HEAD 2>/dev/null || true)
  if [[ "$actual_shared_commit" != "$expected_shared_commit" ]]; then
    echo "❌ $repo_dir/cse-shared is at ${actual_shared_commit:-unknown}, expected $expected_shared_commit."
    all_success=false
  fi

  shared_status=$("${run_as[@]}" git -C "$shared_dir" status --porcelain 2>/dev/null || true)
  if [[ -n "$shared_status" ]]; then
    echo "❌ $repo_dir/cse-shared has local changes:"
    while IFS= read -r line; do
      echo "   $line"
    done <<< "$shared_status"
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
