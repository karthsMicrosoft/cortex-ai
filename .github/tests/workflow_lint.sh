#!/usr/bin/env bash
# .github/tests/workflow_lint.sh
#
# Lint and structural assertions against the GitHub Actions workflow files for US-5.
# Uses `actionlint` if available; falls back to string-content assertions.
#
# Assertions for deploy-backend.yml:
#   - docker buildx  (or az acr build — both build+push patterns allowed)
#   - az acr login   (or az acr build which implicitly authenticates)
#   - az containerapp update  (roll the new image revision)
#
# Assertions for deploy-frontend.yml:
#   - npm ci         (reproducible install)
#   - npm run build  (build the PWA)
#   - Azure/static-web-apps-deploy  (official SWA action)
#
# Usage:
#   bash .github/tests/workflow_lint.sh
#
# Exit code: 0 = all assertions passed, non-zero = at least one failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOWS_DIR="${REPO_ROOT}/.github/workflows"
BACKEND_WF="${WORKFLOWS_DIR}/deploy-backend.yml"
FRONTEND_WF="${WORKFLOWS_DIR}/deploy-frontend.yml"

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
        fail "${description} (pattern '${pattern}' not found in ${file#"${REPO_ROOT}/"})"
    fi
}

assert_contains_re() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "${file}" ]] && grep -qE "${pattern}" "${file}"; then
        pass "${description}"
    else
        fail "${description} (regex '${pattern}' not found in ${file#"${REPO_ROOT}/"})"
    fi
}

echo "============================================================"
echo "  GitHub Actions Workflow Lint — cortex-second-brain US-5"
echo "============================================================"

# ------------------------------------------------------------------
# 1. File existence
# ------------------------------------------------------------------
echo ""
echo "--- File existence ---"
assert_file_exists "${BACKEND_WF}"
assert_file_exists "${FRONTEND_WF}"

# ------------------------------------------------------------------
# 2. actionlint (if available)
# ------------------------------------------------------------------
echo ""
echo "--- actionlint ---"
if which actionlint &>/dev/null; then
    echo "  actionlint found — running on workflow files"
    if [[ -f "${BACKEND_WF}" ]]; then
        if actionlint "${BACKEND_WF}" 2>/dev/null; then
            pass "actionlint: deploy-backend.yml"
        else
            fail "actionlint: deploy-backend.yml has lint errors"
        fi
    fi
    if [[ -f "${FRONTEND_WF}" ]]; then
        if actionlint "${FRONTEND_WF}" 2>/dev/null; then
            pass "actionlint: deploy-frontend.yml"
        else
            fail "actionlint: deploy-frontend.yml has lint errors"
        fi
    fi
else
    echo "  actionlint not installed — using string assertions only (install: https://github.com/rhysd/actionlint)"
fi

# ------------------------------------------------------------------
# 3. deploy-backend.yml assertions
# ------------------------------------------------------------------
echo ""
echo "--- deploy-backend.yml ---"

# Trigger on push to main, paths backend/**
assert_contains_re "${BACKEND_WF}" "branches.*main|push.*main" \
    "deploy-backend.yml triggers on push to main"
assert_contains_re "${BACKEND_WF}" "backend/\*\*|backend/\.\*\*" \
    "deploy-backend.yml triggers on backend/** path changes"

# Docker build/push step — either docker buildx OR az acr build
assert_contains_re "${BACKEND_WF}" "docker buildx|az acr build" \
    "deploy-backend.yml has docker buildx build or az acr build step"

# ACR authentication — either az acr login OR az acr build (which handles auth internally)
assert_contains_re "${BACKEND_WF}" "az acr login|az acr build" \
    "deploy-backend.yml has ACR login or az acr build step"

# Container App update to roll the new image
assert_contains "${BACKEND_WF}" "az containerapp update" \
    "deploy-backend.yml has 'az containerapp update' step"

# Azure login / OIDC
assert_contains_re "${BACKEND_WF}" "azure/login|Az.*Login|AZURE_CREDENTIALS" \
    "deploy-backend.yml has Azure login / OIDC step"

# github.sha or similar tag reference for the image
assert_contains_re "${BACKEND_WF}" "github.sha|GITHUB_SHA|sha" \
    "deploy-backend.yml uses github.sha for image tag"

# ------------------------------------------------------------------
# 4. deploy-frontend.yml assertions
# ------------------------------------------------------------------
echo ""
echo "--- deploy-frontend.yml ---"

# Trigger on push to main, paths frontend/**
assert_contains_re "${FRONTEND_WF}" "branches.*main|push.*main" \
    "deploy-frontend.yml triggers on push to main"
assert_contains_re "${FRONTEND_WF}" "frontend/\*\*|frontend/\.\*\*" \
    "deploy-frontend.yml triggers on frontend/** path changes"

# npm ci — reproducible install
assert_contains "${FRONTEND_WF}" "npm ci" \
    "deploy-frontend.yml has 'npm ci' step"

# npm run build — build the PWA
assert_contains "${FRONTEND_WF}" "npm run build" \
    "deploy-frontend.yml has 'npm run build' step"

# Official Azure Static Web Apps deploy action
assert_contains_re "${FRONTEND_WF}" \
    "Azure/static-web-apps-deploy|azure/static-web-apps-deploy" \
    "deploy-frontend.yml uses Azure/static-web-apps-deploy action"

# SWA API token secret reference
assert_contains_re "${FRONTEND_WF}" "AZURE_STATIC_WEB_APPS_API_TOKEN|secrets.*SWA" \
    "deploy-frontend.yml references SWA API token secret"

# ------------------------------------------------------------------
# 5. Workflow YAML validity (yq or python -c)
# ------------------------------------------------------------------
echo ""
echo "--- YAML validity ---"
_yaml_check_ok=0
for py_cmd in python3 python; do
    if which "${py_cmd}" &>/dev/null; then
        # Confirm python is real (not a Windows Store stub) by checking it prints a version
        if "${py_cmd}" --version 2>/dev/null | grep -qE "Python [0-9]"; then
            _yaml_check_ok=1
            for wf in "${BACKEND_WF}" "${FRONTEND_WF}"; do
                if [[ -f "${wf}" ]]; then
                    wf_name="${wf#"${REPO_ROOT}/"}"
                    if "${py_cmd}" -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" "${wf}" 2>/dev/null; then
                        pass "YAML valid: ${wf_name}"
                    else
                        fail "YAML invalid: ${wf_name}"
                    fi
                fi
            done
            break
        fi
    fi
done
if [[ "${_yaml_check_ok}" -eq 0 ]]; then
    if which yq &>/dev/null; then
        for wf in "${BACKEND_WF}" "${FRONTEND_WF}"; do
            if [[ -f "${wf}" ]]; then
                wf_name="${wf#"${REPO_ROOT}/"}"
                if yq eval '.' "${wf}" &>/dev/null; then
                    pass "YAML valid (yq): ${wf_name}"
                else
                    fail "YAML invalid (yq): ${wf_name}"
                fi
            fi
        done
    else
        echo "  python/yq not available — skipping YAML parse check"
    fi
fi

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
