// infra/modules/container-app.bicep
// Container App Environment + Container App (OQ-7 resolved)
// minReplicas=1 (cold-start avoidance — Container App scale-from-zero takes
// 5–10 s on free tier, painful for voice-capture latency NFR-1)
// (Previously this was justified by APScheduler nightly distill, removed 2026-05-06.)
targetScope = 'resourceGroup'

@description('Base name prefix for resources')
param appName string

@description('Azure region for the resources')
param location string

@description('Container image tag')
param containerImageTag string = 'latest'

@description('Frontend origin for CORS')
param frontendOrigin string

@description('Postgres fully-qualified domain name')
param postgresHost string

@description('ACR login server URL')
param acrLoginServer string

@description('ACR resource name (used as username for registry auth)')
param acrName string

@description('ACR admin password')
@secure()
param acrPassword string

@secure()
@description('Full DATABASE_URL connection string')
param databaseUrl string

@secure()
@description('JWT secret key')
param jwtSecretKey string

@description('Azure OpenAI endpoint')
param openaiEndpoint string

@secure()
@description('Azure OpenAI API key')
param openaiApiKey string

@secure()
@description('Azure Speech key')
param speechKey string

@description('Azure Speech region')
param speechRegion string

@secure()
@description('Azure Storage connection string')
param storageConnectionString string

@description('Azure Vision endpoint')
param visionEndpoint string

@secure()
@description('Azure Vision key')
param visionKey string

// ---------- Container App Environment ----------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {}
}

// ---------- Container App (OQ-7) ----------
// B12 — Log-scrubbing: The Container App does not natively strip query parameters
// from access logs before Application Insights ingestion. The backend is configured
// to NOT log the WebSocket handshake URL. Application Insights telemetry filtering
// is documented in docs/DEPLOYMENT.md (manual Log Analytics workbook redaction step).
// The backend enforces: only "WS connected user={id}" and "Loaded {n} phrases for user {id}"
// are logged at the WS connect path; the raw ?token= URL is never written to any log.
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
          server: acrLoginServer
          username: acrName
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password',                    value: acrPassword }
        { name: 'database-url',                    value: databaseUrl }
        { name: 'jwt-secret-key',                  value: jwtSecretKey }
        { name: 'azure-openai-api-key',            value: openaiApiKey }
        { name: 'azure-speech-key',                value: speechKey }
        { name: 'azure-storage-connection-string', value: storageConnectionString }
        { name: 'azure-vision-key',                value: visionKey }
      ]
    }
    template: {
      containers: [
        {
          name: '${appName}-api'
          image: '${acrLoginServer}/${appName}-api:${containerImageTag}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL',                   secretRef: 'database-url' }
            { name: 'JWT_SECRET_KEY',                 secretRef: 'jwt-secret-key' }
            { name: 'AZURE_OPENAI_ENDPOINT',          value: openaiEndpoint }
            { name: 'AZURE_OPENAI_API_KEY',           secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_API_VERSION',       value: '2024-10-21' }
            { name: 'AZURE_SPEECH_KEY',               secretRef: 'azure-speech-key' }
            { name: 'AZURE_SPEECH_REGION',            value: speechRegion }
            { name: 'AZURE_STORAGE_CONNECTION_STRING',secretRef: 'azure-storage-connection-string' }
            { name: 'AZURE_STORAGE_CONTAINER',        value: 'cortex-media' }
            { name: 'AZURE_VISION_ENDPOINT',          value: visionEndpoint }
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

// ---------- Outputs ----------
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerEnvId   string = containerEnv.id
output containerAppPrincipalId string = containerApp.identity.principalId
