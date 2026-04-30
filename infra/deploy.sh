#!/bin/bash
# infra/deploy.sh - Deploy Cortex to Azure
# Six-step flow: resource group → Bicep → ACR build → containerapp update → alembic upgrade → SWA
set -e

# Variables
RESOURCE_GROUP="${RESOURCE_GROUP:-cortex-rg}"
LOCATION="${LOCATION:-westus2}"
APP_NAME="${APP_NAME:-cortex}"

echo '=== Step 1: Create Resource Group ==='
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo '=== Step 2: Deploy Infrastructure (Bicep) ==='
# Secrets MUST be supplied via env vars when parameters.json does not reference Key Vault.
# Either:
#   (a) Set DB_ADMIN_PASSWORD and JWT_SECRET_KEY env vars before running this script (first-time deploy)
#   (b) Or rename parameters.keyvault-template.json -> parameters.json after bootstrapping KV.
if [ -z "${DB_ADMIN_PASSWORD:-}" ] || [ -z "${JWT_SECRET_KEY:-}" ]; then
  echo "ERROR: DB_ADMIN_PASSWORD and JWT_SECRET_KEY must be set in the environment for first-time deploy."
  echo "       Generate strong random values, export them, and re-run."
  exit 1
fi

DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters infra/parameters.json \
  --parameters appName="$APP_NAME" \
  --parameters dbAdminPassword="$DB_ADMIN_PASSWORD" \
  --parameters jwtSecretKey="$JWT_SECRET_KEY" \
  --output json)

# Extract outputs from the Bicep deployment
ACR_LOGIN_SERVER=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['properties']['outputs']['acrLoginServer']['value'])")
CONTAINER_APP_FQDN=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['properties']['outputs']['containerAppFqdn']['value'])")
SWA_HOST=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['properties']['outputs']['staticWebAppHost']['value'])")
SWA_NAME=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['properties']['outputs']['staticWebAppName']['value'])")

echo '=== Step 3: Build and Push Backend Container ==='
ACR_NAME=$(az acr list --resource-group "$RESOURCE_GROUP" --query '[0].name' -o tsv)
az acr build --registry "$ACR_NAME" --image cortex-api:latest ./backend

echo '=== Step 4: Deploy Backend to Container Apps ==='
az containerapp update \
  --name "${APP_NAME}-api" \
  --resource-group "$RESOURCE_GROUP" \
  --image "${ACR_NAME}.azurecr.io/cortex-api:latest"

echo '=== Step 5: Run Database Migrations ==='
az containerapp exec \
  --name "${APP_NAME}-api" \
  --resource-group "$RESOURCE_GROUP" \
  --command "alembic upgrade head"

echo '=== Step 6: Build and Deploy Frontend ==='
# Update CORS_ORIGINS in the Container App to point at the actual SWA URL (Task 5.3)
FRONTEND_URL="https://${SWA_HOST}"
az containerapp update \
  --name "${APP_NAME}-api" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "CORS_ORIGINS=${FRONTEND_URL},http://localhost:5173"

cd frontend
npm ci
npm run build
cd ..

# Deploy built dist/ to the Static Web App
SWA_TOKEN=$(az staticwebapp secrets list \
  --name "${SWA_NAME}" \
  --resource-group "$RESOURCE_GROUP" \
  --query 'properties.apiKey' -o tsv)

npx @azure/static-web-apps-cli deploy ./frontend/dist \
  --deployment-token "$SWA_TOKEN" \
  --env production

echo ""
echo "=== Deployment Complete! ==="
echo "Frontend: https://${SWA_HOST}"
echo "Backend:  https://${CONTAINER_APP_FQDN}"
