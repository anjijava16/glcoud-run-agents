# Shared helpers for the setup scripts. Sourced, not run.

# Profile file holding your exported keys. Override with PROFILE_FILE=... if yours lives elsewhere.
PROFILE_FILE="${PROFILE_FILE:-${OPENROUTER_KEY_FILE:-$HOME/.zprofile.sh}}"

# read_secret NAME -> prints the value of NAME.
# Order: already exported in this shell -> evaluated from $PROFILE_FILE with zsh ->
# plain "[export] NAME=value" line in $PROFILE_FILE. Prints nothing if not found.
read_secret() {
  local name="$1" val=""
  val="${!name:-}"
  if [ -z "$val" ] && [ -f "$PROFILE_FILE" ]; then
    if command -v zsh >/dev/null 2>&1; then
      val=$(zsh -c 'source "$1" >/dev/null 2>&1; eval "printf %s \"\${$2:-}\""' _ "$PROFILE_FILE" "$name" 2>/dev/null || true)
    fi
    if [ -z "$val" ]; then
      val=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${name}=" "$PROFILE_FILE" | tail -n 1 \
        | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${name}=//; s/[[:space:]]+#.*\$//; s/^[\"']//; s/[\"'][[:space:]]*\$//")
    fi
  fi
  printf '%s' "$val"
}

# retry CMD... -> runs CMD up to 6 times, 15s apart. New service accounts can take a
# minute or two to become visible to IAM ("denied ... or it may not exist"), so every
# IAM binding goes through this instead of failing the whole setup on the first try.
retry() {
  local attempt=1 max=6 wait=15 out
  while true; do
    if out=$("$@" 2>&1); then return 0; fi
    if [ "$attempt" -ge "$max" ]; then
      echo "$out" >&2
      return 1
    fi
    echo "   (not ready yet, retrying in ${wait}s: attempt $attempt/$max)" >&2
    sleep "$wait"; attempt=$((attempt + 1))
  done
}