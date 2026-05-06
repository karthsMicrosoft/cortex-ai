// infra/main.bicep
targetScope = 'resourceGroup'

@description('Base name for all resources')
param appName string = 'cortex'

@description('Azure region for all resources except Azure OpenAI')
param location string = resourceGroup().location

@description('Azure OpenAI region (gpt-4o-mini + text-embedding-3-small not GA in westus2). See OQ-1.')
param openaiLocation string = 'westus'

@description('Container image tag deployed to the API Container App')
param containerImageTag string = 'latest'

@description('Bootstrap image to use when ACR image has not been pushed yet (used on first deploy). The deploy.sh script swaps to the real image via az containerapp update after running az acr build.')
param useBootstrapImage bool = false

@description('Frontend origin used for CORS in the backend')
param frontendOrigin string = 'https://${appName}-app.azurestaticapps.net'

@secure()
@description('PostgreSQL admin password')
param dbAdminPassword string

@secure()
@description('JWT secret key')
param jwtSecretKey string

// ---------- PostgreSQL Flexible Server ----------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${appName}-db'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'cortexadmin'
    administratorLoginPassword: dbAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
  }
}

// Enable pgvector extension via the Azure allowlist
resource pgvectorExt 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'azure.extensions'
  properties: { value: 'VECTOR,UUID-OSSP', source: 'user-override' }
}

// OQ-5: firewall rule so the Container App can reach Postgres.
resource postgresFwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------- Storage Account ----------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${appName}storage'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
}

resource storageBlob 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/cortex-media'
  properties: { publicAccess: 'None' }
}

// ---------- Azure OpenAI (OQ-1: must be in westus, NOT westus2) ----------
resource openai 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-openai'
  location: openaiLocation
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Azure Speech ----------
resource speech 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-speech'
  location: location
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Azure AI Vision ----------
resource vision 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-vision'
  location: location
  kind: 'ComputerVision'
  sku: { name: 'S1' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Container App Environment ----------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {}
}

// ---------- Container Registry ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${appName}acr'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

// ---------- Container App (OQ-7) ----------
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-api'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'           // enables HTTP/1.1 + WebSocket
        allowInsecure: false        // HTTPS only
        traffic: [ { latestRevision: true, weight: 100 } ]
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password',                    value: acr.listCredentials().passwords[0].value }
        { name: 'database-url',                    value: 'postgresql+asyncpg://cortexadmin:${dbAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/cortex' }
        { name: 'jwt-secret-key',                  value: jwtSecretKey }
        { name: 'azure-openai-api-key',            value: openai.listKeys().key1 }
        { name: 'azure-speech-key',                value: speech.listKeys().key1 }
        { name: 'azure-storage-connection-string', value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=core.windows.net' }
        { name: 'azure-vision-key',                value: vision.listKeys().key1 }
      ]
    }
    template: {
      containers: [
        {
          name: '${appName}-api'
          image: useBootstrapImage ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : '${acr.properties.loginServer}/${appName}-api:${containerImageTag}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL',                   secretRef: 'database-url' }
            { name: 'JWT_SECRET_KEY',                 secretRef: 'jwt-secret-key' }
            { name: 'AZURE_OPENAI_ENDPOINT',          value: openai.properties.endpoint }
            { name: 'AZURE_OPENAI_API_KEY',           secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_API_VERSION',       value: '2024-10-21' }
            { name: 'AZURE_SPEECH_KEY',               secretRef: 'azure-speech-key' }
            { name: 'AZURE_SPEECH_REGION',            value: location }
            { name: 'AZURE_STORAGE_CONNECTION_STRING',secretRef: 'azure-storage-connection-string' }
            { name: 'AZURE_STORAGE_CONTAINER',        value: 'cortex-media' }
            { name: 'AZURE_VISION_ENDPOINT',          value: vision.properties.endpoint }
            { name: 'AZURE_VISION_KEY',               secretRef: 'azure-vision-key' }
            { name: 'CORS_ORIGINS',                   value: frontendOrigin }
            { name: 'ENVIRONMENT',                    value: 'production' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1                          // Cold-start avoidance (no background-job dep; scheduler removed 2026-05-06)
        maxReplicas: 3
        rules: [
          {
            name: 'cpu-rule'
            custom: {
              type: 'cpu'
              metadata: { type: 'Utilization', value: '70' }
            }
          }
        ]
      }
    }
  }
}

// ---------- Static Web App (OQ-6) ----------
resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${appName}-app'
  location: location
  sku: { name: 'Free', tier: 'Free' }
  properties: {
    repositoryUrl: ''        // CI/CD wiring done by deploy-frontend.yml; this resource hosts the static site only
    branch: ''
    buildProperties: {
      appLocation: 'frontend'
      apiLocation: ''
      outputLocation: 'dist'
    }
  }
}

// ---------- Outputs ----------
output postgresHost      string = postgres.properties.fullyQualifiedDomainName
output storageAccountName string = storage.name
output openaiEndpoint    string = openai.properties.endpoint
output openaiRegion      string = openaiLocation
output speechRegion      string = location
output visionEndpoint    string = vision.properties.endpoint
output acrLoginServer    string = acr.properties.loginServer
output containerAppFqdn  string = containerApp.properties.configuration.ingress.fqdn
output staticWebAppName  string = staticWebApp.name
output staticWebAppHost  string = staticWebApp.properties.defaultHostname
