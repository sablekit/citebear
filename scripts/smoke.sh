#!/usr/bin/env bash
#
# Post-deploy production smoke check (issue #61).
#
# A Vercel deploy can report "Ready" (built) yet be dead at runtime — a
# packaging strip, a missing env var, a broken proxy route. Nothing in the
# normal test suite touches the deployed instance. This walks the critical
# path against production and fails loudly if it is broken:
#
#   1. GET  <API_URL>/healthz            -> 200            (the API function boots)
#   2. POST <WEB_URL>/api/chat           -> streamed answer that cites a source
#      (web proxy -> api -> Neon -> gateway, the whole chain in one request)
#
# Shallow by design: it answers "is the critical path even alive?", not feature
# coverage (the golden set already validates retrieval logic).
set -euo pipefail

WEB_URL="${WEB_URL:-https://citebear.com}"
API_URL="${API_URL:-https://citebear-api.vercel.app}"

fail() {
  echo "SMOKE FAIL: $*" >&2
  exit 1
}

# 1. Health check, with a readiness retry so a deploy that is still settling
#    (or a sibling project still deploying) doesn't cause a false alarm.
echo "==> Waiting for ${API_URL}/healthz"
health_ok=""
for attempt in $(seq 1 15); do
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 20 "${API_URL}/healthz" 2>/dev/null || true)"
  if [ "${code}" = "200" ]; then
    health_ok="yes"
    echo "    healthz 200 (attempt ${attempt})"
    break
  fi
  echo "    healthz ${code:-000}, retrying in 6s (attempt ${attempt}/15)"
  sleep 6
done
[ -n "${health_ok}" ] || fail "healthz never returned 200 at ${API_URL}/healthz"

# 2. One real end-to-end chat turn through the web proxy. The NIST password-length
#    question is answerable from the preloaded library and reliably cites sources.
echo "==> Chat turn through ${WEB_URL}/api/chat"
session_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
body="$(printf '{"sessionId":"%s","message":"What does NIST recommend for minimum password length?"}' "${session_id}")"

response="$(curl -sS --max-time 120 \
  -X POST "${WEB_URL}/api/chat" \
  -H 'content-type: application/json' \
  -d "${body}" 2>/dev/null || true)"

[ -n "${response}" ] || fail "chat returned an empty response"

# The web proxy adapts the API's SSE into the AI SDK UI message stream: a
# 'data-sources' part carries the citations, 'text-delta' parts carry the answer.
if ! grep -q '"type":"data-sources"' <<<"${response}"; then
  echo "---- response (truncated) ----" >&2
  printf '%s\n' "${response}" | head -c 2000 >&2
  fail "chat streamed no citations (no data-sources part) — retrieval path is broken"
fi
if ! grep -q '"type":"text-delta"' <<<"${response}"; then
  fail "chat streamed no answer tokens (no text-delta part)"
fi
if grep -q '"type":"error"' <<<"${response}"; then
  echo "---- response (truncated) ----" >&2
  printf '%s\n' "${response}" | head -c 2000 >&2
  fail "chat stream carried an error part"
fi

echo "SMOKE OK: healthz 200 + a cited, streamed chat answer"
