#!/bin/bash
# infra/teardown.sh - Tear down the Cortex Azure resource group
# WARNING: This permanently deletes ALL resources in the resource group.
# For dev iteration only — NEVER invoked from CI.
set -e

RESOURCE_GROUP="${RESOURCE_GROUP:-cortex-rg}"

echo "=== Tearing down resource group: ${RESOURCE_GROUP} ==="
echo "This will permanently delete all resources. Press Ctrl+C within 10 seconds to abort."
sleep 10

az group delete --name "$RESOURCE_GROUP" --yes

echo "=== Teardown complete ==="
