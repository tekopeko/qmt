#!/bin/sh
# Stop hook: UI work is not finished until it has been checked on a phone.
#
# When the templates or static CSS/JS differ from the last stamped state, this
# runs the audit's phone pass by itself: every page as guest / client / owner
# at 390px and 360px with touch emulation, checking sideways scroll, anything
# sticking out of its container (the topbar pill included), tap targets,
# labels, alt text, headings and contrast. A pass stamps the files and the stop
# goes through in silence. A failure blocks the stop and hands Claude the
# findings. It never loops: the same failing state blocks once per session.
#
# What it cannot do is look at the page. It proves the measurable half of
# "renders correctly on a phone"; a screenshot is still how taste gets checked.
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
input=$(cat 2>/dev/null)
sid=$(printf '%s' "$input" | jq -r '.session_id // "no-session"' 2>/dev/null)
fp=$("$root/.claude/hooks/ui-fingerprint.sh" 2>/dev/null)
[ -n "$fp" ] || exit 0                                    # cannot fingerprint: never block on our own failure
[ "$fp" = "$(cat "$root/.claude/ui-audit.stamp" 2>/dev/null)" ] && exit 0      # these exact files already passed
seen="$root/.claude/ui-audit.blocked"
[ "$(cat "$seen" 2>/dev/null)" = "$sid $fp" ] && exit 0   # already blocked for this exact state: do not loop
block() {
  printf '%s' "$sid $fp" > "$seen"
  jq -cn --arg r "$1" '{decision: "block", reason: $r}'
  exit 0
}
py="$root/.venv/bin/python"; base="${QMT_AUDIT_URL:-http://127.0.0.1:8100}"
audit="$root/.claude/skills/qmt-design/scripts/audit.py"
[ -x "$py" ] || block "UI files changed since the last passing phone check, and $py is missing, so the check could not run. Create the venv (see CLAUDE.md, Commands), then run: python $audit --phone"
curl -s -o /dev/null --max-time 3 "$base/healthz" || block "UI files changed since the last passing phone check, and the dev server at $base is not running, so nothing was checked. Start it (python serve.py --port 8100, demo seed loaded), then run: .venv/bin/python .claude/skills/qmt-design/scripts/audit.py --phone"
out=$("$py" "$audit" --phone "$base" 2>&1) && exit 0      # passed: the audit wrote the stamp
block "The phone check FAILED on the UI as it is now (390px and 360px, touch, guest / client / owner). Fix these, then finish again:
$(printf '%s' "$out" | grep -v '^[[:space:]]*$' | tail -30)"
