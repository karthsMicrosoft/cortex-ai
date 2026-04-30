#!/usr/bin/env bash
# infra/tests/test_deploy_script.sh
#
# Structural assertions against infra/deploy.sh verifying the six-step deploy flow
# per spec § 5.2 and design.md § "Bicep Template (canonical)".
#
# The six required steps are:
#   1. Resource group create  (az group create)
#   2. Bicep deploy           (az deployment group create)
#   3. ACR build              (az acr build)
#   4. Container App update   (az containerapp update)
#   5. Alembic upgrade head   (alembic upgrade head via containerapp exec)
#   6. Static Web App deploy  (az staticwebapp create OR Azure/static-web-apps-deploy)
#
# Usage:
#   bash infra/tests/test_deploy_script.sh
#
# Exit code: 0 = all assertions passed, non-zero = at least one failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_SH="${REPO_ROOT}/infra/deploy.sh"
TEARDOWN_SH="${REPO_ROOT}/infra/teardown.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

assert_file_exists() {
    local file="$1"
    if [[ -f "${file}" ]]; then
        pass "File exists: ${file#"${REPO_ROOT}/"}"
    else
        fail "File missing: ${file#"${REPO_ROOT}/"}"
    fi
}

assert_contains() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "${file}" ]] && grep -qF "${pattern}" "${file}"; then
        pass "${description}"
    else
        fail "${description} (pattern not found: '${pattern}' in ${file#"${REPO_ROOT}/"})"
    fi
}

assert_contains_re() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "${file}" ]] && grep -qE "${pattern}" "${file}"; then
        pass "${description}"
    else
        fail "${description} (regex not found: '${pattern}' in ${file#"${REPO_ROOT}/"})"
    fi
}

echo "============================================================"
echo "  deploy.sh Structure Tests — cortex-second-brain US-5"
echo "============================================================"

# ------------------------------------------------------------------
# 1. File existence
# ------------------------------------------------------------------
echo ""
echo "--- File existence ---"
assert_file_exists "${DEPLOY_SH}"
assert_file_exists "${TEARDOWN_SH}"

# ------------------------------------------------------------------
# 2. Script hygiene
# ------------------------------------------------------------------
echo ""
echo "--- Script hygiene ---"
assert_contains "${DEPLOY_SH}" "set -e" \
    "deploy.sh has 'set -e' (fail-fast)"
assert_contains_re "${DEPLOY_SH}" "^#!/" \
    "deploy.sh has a shebang line"

# ------------------------------------------------------------------
# 3. Step 1 — Create resource group
# ------------------------------------------------------------------
echo ""
echo "--- Step 1: Resource group create ---"
assert_contains "${DEPLOY_SH}" "az group create" \
    "deploy.sh has 'az group create' (Step 1)"

# ------------------------------------------------------------------
# 4. Step 2 — Deploy Bicep
# ------------------------------------------------------------------
echo ""
echo "--- Step 2: Bicep deployment ---"
assert_contains "${DEPLOY_SH}" "az deployment group create" \
    "deploy.sh has 'az deployment group create' (Step 2)"
assert_contains "${DEPLOY_SH}" "main.bicep" \
    "deploy.sh references main.bicep"

# ------------------------------------------------------------------
# 5. Step 3 — ACR build
# ------------------------------------------------------------------
echo ""
echo "--- Step 3: ACR build ---"
assert_contains "${DEPLOY_SH}" "az acr build" \
    "deploy.sh has 'az acr build' (Step 3)"

# ------------------------------------------------------------------
# 6. Step 4 — Container App update
# ------------------------------------------------------------------
echo ""
echo "--- Step 4: Container App update ---"
assert_contains "${DEPLOY_SH}" "az containerapp update" \
    "deploy.sh has 'az containerapp update' (Step 4)"

# ------------------------------------------------------------------
# 7. Step 5 — Alembic upgrade head
# ------------------------------------------------------------------
echo ""
echo "--- Step 5: Alembic migration ---"
assert_contains "${DEPLOY_SH}" "alembic upgrade head" \
    "deploy.sh has 'alembic upgrade head' (Step 5)"
assert_contains_re "${DEPLOY_SH}" "containerapp exec|containerapp run" \
    "deploy.sh runs alembic via containerapp exec/run"

# ------------------------------------------------------------------
# 8. Step 6 — Static Web App deploy
# ------------------------------------------------------------------
echo ""
echo "--- Step 6: Static Web App deploy ---"
assert_contains_re "${DEPLOY_SH}" "staticwebapp|static-web-apps" \
    "deploy.sh has Static Web App deployment step (Step 6)"
assert_contains_re "${DEPLOY_SH}" "npm run build|npm ci" \
    "deploy.sh builds the frontend (npm run build or npm ci)"

# ------------------------------------------------------------------
# 9. Output printed at end
# ------------------------------------------------------------------
echo ""
echo "--- Output URLs ---"
assert_contains_re "${DEPLOY_SH}" "Frontend|frontend.*url|azurestaticapps" \
    "deploy.sh prints frontend URL at end"
assert_contains_re "${DEPLOY_SH}" "Backend|backend.*url|azurecontainerapps" \
    "deploy.sh prints backend URL at end"

# ------------------------------------------------------------------
# 10. teardown.sh — az group delete
# ------------------------------------------------------------------
echo ""
echo "--- teardown.sh ---"
assert_contains "${TEARDOWN_SH}" "az group delete" \
    "teardown.sh has 'az group delete'"
assert_contains_re "${TEARDOWN_SH}" "\-\-yes" \
    "teardown.sh uses --yes flag (non-interactive)"

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "============================================================"

if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
