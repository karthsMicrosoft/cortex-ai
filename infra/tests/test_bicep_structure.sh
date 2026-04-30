#!/usr/bin/env bash
# infra/tests/test_bicep_structure.sh
#
# Structural assertions against the Bicep IaC files for US-5.
# Gated by `which az` — if the Azure CLI is not installed, falls back to
# string-content assertions only (no `az bicep build` lint).
#
# Usage:
#   bash infra/tests/test_bicep_structure.sh
#
# Exit code: 0 = all assertions passed, non-zero = at least one failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INFRA_DIR="${REPO_ROOT}/infra"
MAIN_BICEP="${INFRA_DIR}/main.bicep"
MODULES_DIR="${INFRA_DIR}/modules"

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
echo "  Bicep Structure Tests — cortex-second-brain US-5"
echo "============================================================"

# ------------------------------------------------------------------
# 1. File existence
# ------------------------------------------------------------------
echo ""
echo "--- File existence checks ---"
assert_file_exists "${MAIN_BICEP}"
assert_file_exists "${INFRA_DIR}/parameters.json"
assert_file_exists "${INFRA_DIR}/deploy.sh"
assert_file_exists "${INFRA_DIR}/teardown.sh"
assert_file_exists "${MODULES_DIR}/postgres.bicep"
assert_file_exists "${MODULES_DIR}/storage.bicep"
assert_file_exists "${MODULES_DIR}/cognitive-services.bicep"
assert_file_exists "${MODULES_DIR}/container-app.bicep"
assert_file_exists "${MODULES_DIR}/static-web-app.bicep"

# ------------------------------------------------------------------
# 2. az bicep build lint (if Azure CLI available)
# ------------------------------------------------------------------
echo ""
echo "--- Bicep lint (az bicep build) ---"
if which az &>/dev/null; then
    echo "  Azure CLI found — running az bicep build lint"
    _bicep_tmp_dir="$(mktemp -d 2>/dev/null || echo "${TEMP:-/tmp}/bicep_test_$$")"
    mkdir -p "${_bicep_tmp_dir}"
    _bicep_out="${_bicep_tmp_dir}/out.json"
    for bicep_file in \
        "${MAIN_BICEP}" \
        "${MODULES_DIR}/postgres.bicep" \
        "${MODULES_DIR}/storage.bicep" \
        "${MODULES_DIR}/cognitive-services.bicep" \
        "${MODULES_DIR}/container-app.bicep" \
        "${MODULES_DIR}/static-web-app.bicep"
    do
        if [[ -f "${bicep_file}" ]]; then
            # Use --outfile with a real temp path (Windows az bicep does not support /dev/null)
            if az bicep build --file "${bicep_file}" --outfile "${_bicep_out}" 2>/dev/null; then
                pass "az bicep build: ${bicep_file#"${REPO_ROOT}/"}"
            else
                fail "az bicep build: ${bicep_file#"${REPO_ROOT}/"}"
            fi
        fi
    done
    rm -rf "${_bicep_tmp_dir}" 2>/dev/null || true
else
    echo "  Azure CLI not found — skipping az bicep build (using string assertions only)"
fi

# ------------------------------------------------------------------
# 3. main.bicep — required parameters
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: required parameters ---"
assert_contains "${MAIN_BICEP}" "param openaiLocation" \
    "main.bicep has 'param openaiLocation' (OQ-1)"
assert_contains "${MAIN_BICEP}" "param appName" \
    "main.bicep has 'param appName'"
assert_contains "${MAIN_BICEP}" "param location" \
    "main.bicep has 'param location'"
assert_contains "${MAIN_BICEP}" "param containerImageTag" \
    "main.bicep has 'param containerImageTag'"
assert_contains "${MAIN_BICEP}" "param frontendOrigin" \
    "main.bicep has 'param frontendOrigin'"
assert_contains "${MAIN_BICEP}" "param dbAdminPassword" \
    "main.bicep has '@secure() param dbAdminPassword'"
assert_contains "${MAIN_BICEP}" "param jwtSecretKey" \
    "main.bicep has '@secure() param jwtSecretKey'"

# ------------------------------------------------------------------
# 4. main.bicep — Postgres + pgvector + firewall rule (OQ-5)
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Postgres resources ---"
assert_contains "${MAIN_BICEP}" "Microsoft.DBforPostgreSQL/flexibleServers" \
    "main.bicep has Postgres flexibleServers resource"
assert_contains "${MAIN_BICEP}" "Standard_B1ms" \
    "main.bicep uses Standard_B1ms SKU"
assert_contains "${MAIN_BICEP}" "VECTOR,UUID-OSSP" \
    "main.bicep enables VECTOR and UUID-OSSP extensions"
assert_contains "${MAIN_BICEP}" "AllowAllAzureServicesAndResourcesWithinAzureIps" \
    "main.bicep has Postgres firewall rule (OQ-5)"
assert_contains "${MAIN_BICEP}" "firewallRules" \
    "main.bicep has firewallRules resource type"

# ------------------------------------------------------------------
# 5. main.bicep — Storage Account
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Storage Account ---"
assert_contains "${MAIN_BICEP}" "Microsoft.Storage/storageAccounts" \
    "main.bicep has Storage Account resource"
assert_contains "${MAIN_BICEP}" "StorageV2" \
    "main.bicep uses StorageV2 kind"
assert_contains "${MAIN_BICEP}" "Standard_LRS" \
    "main.bicep uses Standard_LRS SKU"
assert_contains "${MAIN_BICEP}" "cortex-media" \
    "main.bicep has cortex-media blob container"

# ------------------------------------------------------------------
# 6. main.bicep — Azure OpenAI (OQ-1: openaiLocation)
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Azure OpenAI ---"
assert_contains "${MAIN_BICEP}" "Microsoft.CognitiveServices/accounts" \
    "main.bicep has CognitiveServices accounts"
assert_contains "${MAIN_BICEP}" "kind: 'OpenAI'" \
    "main.bicep has OpenAI kind"
assert_contains "${MAIN_BICEP}" "openaiLocation" \
    "main.bicep uses openaiLocation for OpenAI resource (OQ-1)"

# ------------------------------------------------------------------
# 7. main.bicep — Azure Speech
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Azure Speech ---"
assert_contains "${MAIN_BICEP}" "SpeechServices" \
    "main.bicep has SpeechServices resource"

# ------------------------------------------------------------------
# 8. main.bicep — Azure AI Vision
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Azure AI Vision ---"
assert_contains "${MAIN_BICEP}" "ComputerVision" \
    "main.bicep has ComputerVision resource"
assert_contains "${MAIN_BICEP}" "'S1'" \
    "main.bicep uses S1 SKU for Vision"

# ------------------------------------------------------------------
# 9. main.bicep — Container App Environment + ACR
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Container App Environment + ACR ---"
assert_contains "${MAIN_BICEP}" "Microsoft.App/managedEnvironments" \
    "main.bicep has Container App Environment"
assert_contains "${MAIN_BICEP}" "Microsoft.ContainerRegistry/registries" \
    "main.bicep has ACR resource"
assert_contains "${MAIN_BICEP}" "sku: { name: 'Basic' }" \
    "main.bicep uses ACR Basic SKU"

# ------------------------------------------------------------------
# 10. main.bicep — Container App (OQ-7)
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Container App resource (OQ-7) ---"
assert_contains "${MAIN_BICEP}" "Microsoft.App/containerApps" \
    "main.bicep has Microsoft.App/containerApps resource"
assert_contains "${MAIN_BICEP}" "identity: { type: 'SystemAssigned' }" \
    "main.bicep Container App has SystemAssigned identity"
assert_contains "${MAIN_BICEP}" "transport: 'auto'" \
    "main.bicep Container App ingress transport is 'auto' (WebSocket support)"
assert_contains "${MAIN_BICEP}" "allowInsecure: false" \
    "main.bicep Container App has allowInsecure: false"
assert_contains "${MAIN_BICEP}" "minReplicas: 1" \
    "main.bicep Container App has minReplicas: 1 (B14 — APScheduler alive)"
assert_contains "${MAIN_BICEP}" "maxReplicas: 3" \
    "main.bicep Container App has maxReplicas: 3"
assert_contains "${MAIN_BICEP}" "'/api/health'" \
    "main.bicep has liveness/readiness probes on /api/health"
assert_contains "${MAIN_BICEP}" "database-url" \
    "main.bicep has database-url secret"
assert_contains "${MAIN_BICEP}" "jwt-secret-key" \
    "main.bicep has jwt-secret-key secret"

# ------------------------------------------------------------------
# 11. main.bicep — Static Web App (OQ-6)
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: Static Web App (OQ-6) ---"
assert_contains "${MAIN_BICEP}" "Microsoft.Web/staticSites" \
    "main.bicep has Microsoft.Web/staticSites resource (OQ-6)"
assert_contains_re "${MAIN_BICEP}" "'Free'" \
    "main.bicep Static Web App uses Free SKU"

# ------------------------------------------------------------------
# 12. main.bicep — Outputs
# ------------------------------------------------------------------
echo ""
echo "--- main.bicep: required outputs ---"
assert_contains "${MAIN_BICEP}" "output containerAppFqdn" \
    "main.bicep has output containerAppFqdn"
assert_contains "${MAIN_BICEP}" "output postgresHost" \
    "main.bicep has output postgresHost"
assert_contains "${MAIN_BICEP}" "output storageAccountName" \
    "main.bicep has output storageAccountName"
assert_contains "${MAIN_BICEP}" "output openaiEndpoint" \
    "main.bicep has output openaiEndpoint"
assert_contains "${MAIN_BICEP}" "output openaiRegion" \
    "main.bicep has output openaiRegion"
assert_contains "${MAIN_BICEP}" "output speechRegion" \
    "main.bicep has output speechRegion"
assert_contains "${MAIN_BICEP}" "output visionEndpoint" \
    "main.bicep has output visionEndpoint"
assert_contains "${MAIN_BICEP}" "output acrLoginServer" \
    "main.bicep has output acrLoginServer"
assert_contains "${MAIN_BICEP}" "output staticWebAppName" \
    "main.bicep has output staticWebAppName"
assert_contains "${MAIN_BICEP}" "output staticWebAppHost" \
    "main.bicep has output staticWebAppHost"

# ------------------------------------------------------------------
# 13. Modules — structural spot-checks
# ------------------------------------------------------------------
echo ""
echo "--- modules/postgres.bicep ---"
POSTGRES_MODULE="${MODULES_DIR}/postgres.bicep"
assert_contains "${POSTGRES_MODULE}" "Microsoft.DBforPostgreSQL/flexibleServers" \
    "postgres.bicep has flexibleServers resource"
assert_contains "${POSTGRES_MODULE}" "Standard_B1ms" \
    "postgres.bicep uses Standard_B1ms"
assert_contains "${POSTGRES_MODULE}" "AllowAllAzureServicesAndResourcesWithinAzureIps" \
    "postgres.bicep has Azure firewall rule (OQ-5)"
assert_contains "${POSTGRES_MODULE}" "VECTOR,UUID-OSSP" \
    "postgres.bicep enables pgvector extension"

echo ""
echo "--- modules/storage.bicep ---"
STORAGE_MODULE="${MODULES_DIR}/storage.bicep"
assert_contains "${STORAGE_MODULE}" "Microsoft.Storage/storageAccounts" \
    "storage.bicep has Storage Account resource"
assert_contains "${STORAGE_MODULE}" "StorageV2" \
    "storage.bicep uses StorageV2 kind"

echo ""
echo "--- modules/cognitive-services.bicep ---"
COG_MODULE="${MODULES_DIR}/cognitive-services.bicep"
assert_contains "${COG_MODULE}" "OpenAI" \
    "cognitive-services.bicep has OpenAI account"
assert_contains "${COG_MODULE}" "SpeechServices" \
    "cognitive-services.bicep has Speech account"
assert_contains "${COG_MODULE}" "ComputerVision" \
    "cognitive-services.bicep has Vision account"
assert_contains "${COG_MODULE}" "openaiLocation" \
    "cognitive-services.bicep uses openaiLocation param (OQ-1)"

echo ""
echo "--- modules/container-app.bicep ---"
CA_MODULE="${MODULES_DIR}/container-app.bicep"
assert_contains "${CA_MODULE}" "Microsoft.App/containerApps" \
    "container-app.bicep has containerApps resource"
assert_contains "${CA_MODULE}" "minReplicas: 1" \
    "container-app.bicep has minReplicas: 1 (B14)"
assert_contains "${CA_MODULE}" "transport: 'auto'" \
    "container-app.bicep has transport: 'auto'"
assert_contains "${CA_MODULE}" "allowInsecure: false" \
    "container-app.bicep has allowInsecure: false"
assert_contains "${CA_MODULE}" "SystemAssigned" \
    "container-app.bicep has SystemAssigned identity"

echo ""
echo "--- modules/static-web-app.bicep ---"
SWA_MODULE="${MODULES_DIR}/static-web-app.bicep"
assert_contains "${SWA_MODULE}" "Microsoft.Web/staticSites" \
    "static-web-app.bicep has staticSites resource"
assert_contains "${SWA_MODULE}" "Free" \
    "static-web-app.bicep uses Free SKU"

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
