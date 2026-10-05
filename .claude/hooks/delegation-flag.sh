#!/bin/sh
# SessionStart hook: tells the model whether small tasks get delegated to Opus.
# The rule itself is in CLAUDE.md ("Models"); this script only reports the flag.
#
#   flag   QMT_DELEGATE = on | off     (missing, or anything else, means OFF)
#   where  .claude/settings.local.json, under "env"  (untracked, per machine);
#          an exported QMT_DELEGATE is the fallback
#
# Run it by hand to see the current value:  .claude/hooks/delegation-flag.sh
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
val=$(jq -r '.env.QMT_DELEGATE // empty' "$root/.claude/settings.local.json" 2>/dev/null)
[ -n "$val" ] || val="${QMT_DELEGATE:-}"
case "$(printf '%s' "$val" | tr '[:upper:]' '[:lower:]')" in
  on|1|true|yes)
    msg='Delegation is ON (QMT_DELEGATE): hand small, self-contained tasks to the opus-worker agent and review its diff before accepting, as CLAUDE.md "Models" describes.' ;;
  *)
    msg='Delegation is OFF (QMT_DELEGATE): do the work directly. Use opus-worker only when the owner asks for it in the conversation.' ;;
esac
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg m "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $m}}'
else
  printf '%s\n' "$msg"
fi
