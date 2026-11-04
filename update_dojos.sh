#!/usr/bin/env bash

# Sourceable so discovery and selection can be tested without publishing anything.
usage() {
  cat <<'HELP'
Usage: update_dojos.sh [--prod] [--list] [--root DIRECTORY] [--api-url URL]

Query the backend for current-semester dojos and match them to local repos
with dojo.yml, an executable update_dojo.sh, and a cse-shared submodule.

The shared repo is committed (if changed) and pushed. Deployment then follows
these choices: y = all, n = none (default), c = choose each dojo with y/n.
--prod  Update all discovered dojos without prompting.
--list  Only list discovered dojos; do not commit, push, or deploy.
--root  Find dojo repos directly under DIRECTORY instead.
--api-url  Override the current-semester backend endpoint.
HELP
}

# Output: one repository path per line. Check .gitmodules, not directory names.
discover_dojos() {
  local root="$1" repo key path url top
  for repo in "$root"/*; do
    [[ -d "$repo" && -f "$repo/dojo.yml" && -x "$repo/update_dojo.sh" && -f "$repo/.gitmodules" ]] || continue
    top=$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null) || continue
    [[ "$(realpath "$repo")" == "$(realpath "$top")" ]] || continue
    while read -r key path; do
      url=$(git config -f "$repo/.gitmodules" --get "${key%.path}.url") || continue
      if [[ "$path" == cse-shared && "$url" =~ (^|[/:])cse-shared(\.git)?$ ]]; then
        printf '%s\n' "$repo"
        break
      fi
    done < <(git config -f "$repo/.gitmodules" --get-regexp '^submodule\..*\.path$' || true)
  done
}

read_choice() {
  local prompt="$1" allowed="$2" answer
  while true; do
    printf '%s' "$prompt" >&2
    if ! IFS= read -r answer; then answer=n; fi
    answer=${answer,,}
    case "$answer" in
      '') printf 'n\n'; return ;;
      y|n) printf '%s\n' "$answer"; return ;;
      c) if [[ "$allowed" == ync ]]; then printf 'c\n'; return; fi ;;
    esac
    printf 'Please enter %s (Enter defaults to n).\n' "$allowed" >&2
  done
}

# Sets the selected array in the caller; prompts finish before parallel updates.
select_dojos() {
  local prod="$1" answer repo
  shift
  selected=()
  [[ "$#" -gt 0 ]] || return 0
  if [[ "$prod" == true ]]; then
    selected=("$@")
    return 0
  fi
  answer=$(read_choice 'Push and update the discovered dojos? [y/N/c] ' ync)
  case "$answer" in
    y) selected=("$@") ;;
    c)
      for repo in "$@"; do
        answer=$(read_choice "Push and update $(basename "$repo") in pwn.college? [y/N] " yn)
        [[ "$answer" != y ]] || selected+=("$repo")
      done
      ;;
  esac
}

publish_shared() {
  "${run_as[@]}" git add . || return 1
  if ! "${run_as[@]}" git diff --cached --quiet; then
    "${run_as[@]}" git commit -m 'Update dojo scripts' || return 1
  fi
  "${run_as[@]}" git push || return 1
}

update_selected() {
  local expected="$1" repo pid actual dirty failed=false
  shift
  local -A pids=()
  # These scripts may prompt before overwriting a dirty submodule. Preserve the
  # work and fail before launching any deployments instead of prompting in parallel.
  for repo in "$@"; do
    if [[ ! -e "$repo/cse-shared/.git" ]]; then
      printf 'Missing cse-shared checkout: %s\n' "$repo" >&2
      return 1
    fi
    dirty=$("${run_as[@]}" git -C "$repo/cse-shared" status --porcelain) || return 1
    if [[ -n "$dirty" ]]; then
      printf 'Local changes in %s/cse-shared; resolve them before deployment.\n' "$repo" >&2
      return 1
    fi
  done
  for repo in "$@"; do
    printf 'Running %s/update_dojo.sh\n' "$repo"
    (cd "$repo" && "${run_as[@]}" ./update_dojo.sh </dev/null) &
    pids["$repo"]=$!
  done
  for repo in "$@"; do
    pid=${pids[$repo]}
    if wait "$pid"; then
      printf 'Update completed: %s\n' "$repo"
    else
      printf 'Update failed: %s\n' "$repo" >&2
      failed=true
    fi
    actual=$("${run_as[@]}" git -C "$repo/cse-shared" rev-parse HEAD) || actual=unknown
    if [[ "$actual" != "$expected" ]]; then
      printf '%s/cse-shared is at %s; expected %s\n' "$repo" "$actual" "$expected" >&2
      failed=true
    fi
    dirty=$("${run_as[@]}" git -C "$repo/cse-shared" status --porcelain) || { dirty='status check failed'; }
    if [[ -n "$dirty" ]]; then
      printf '%s/cse-shared has local changes: %s\n' "$repo" "$dirty" >&2
      failed=true
    fi
  done
  [[ "$failed" == false ]]
}

main() {
  local shared_dir root prod=false list=false expected discovery
  local api_url=${CSE_DOJOS_API_URL:-https://api.cse545.com/api/dojos/current-semester}
  shared_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || return 1
  root=$(dirname "$shared_dir")
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --prod) prod=true ;;
      --list) list=true ;;
      --api-url)
        [[ "$#" -ge 2 && -n "$2" ]] || { printf "%s\n" "--api-url requires a URL" >&2; return 2; }
        api_url=$2
        shift ;;
      --root)
        if [[ "$#" -lt 2 || ! -d "$2" ]]; then
          printf '%s\n' '--root requires an existing directory' >&2
          return 2
        fi
        root=$(cd -- "$2" && pwd -P) || return 1
        shift ;;
      -h|--help) usage; return 0 ;;
      *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; return 2 ;;
    esac
    shift
  done
  local -a repos=() selected=() run_as=()
  # Capture status explicitly: process substitution alone would hide API errors.
  discovery=$(discover_dojos "$root" | /opt/class_sync/apivenv/bin/python "$shared_dir/resolve_current_dojos.py" --api-url "$api_url") || return 1
  if [[ -n "$discovery" ]]; then mapfile -t repos <<< "$discovery"; fi
  printf 'Matched %d current-semester dojo(s):\n' "${#repos[@]}"
  if [[ "${#repos[@]}" -gt 0 ]]; then printf '  %s\n' "${repos[@]}"; fi
  if [[ "$list" == true ]]; then return 0; fi
  if [[ "$(stat -c %U "$shared_dir")" == duck && "$(id -un)" != duck ]]; then
    run_as=(sudo -H -u duck --)
    printf '%s\n' 'Running updates as duck (shared repo owner).'
  fi
  select_dojos "$prod" "${repos[@]}"
  cd "$shared_dir" || return 1
  publish_shared || return 1
  expected=$("${run_as[@]}" git rev-parse HEAD) || return 1
  if [[ "${#selected[@]}" -eq 0 ]]; then
    printf '%s\n' 'Shared repo pushed; no dojos selected for deployment.'
    return 0
  fi
  if update_selected "$expected" "${selected[@]}"; then
    printf '%s\n' 'All selected dojo updates completed successfully.'
  else
    printf '%s\n' 'One or more dojo updates failed.' >&2
    return 1
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
