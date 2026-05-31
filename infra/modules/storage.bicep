// infra/modules/storage.bicep
// Azure Storage Account (StorageV2 LRS) + cortex-media blob container
targetScope = 'resourceGroup'

@description('Base name prefix for the resource')
param appName string

@description('Azure region for the resource')
param location string

@description('Frontend origin allowed by Blob CORS (Round 31). Defaults to the SWA URL convention.')
param frontendOrigin string = 'https://${appName}-app.azurestaticapps.net'

// ---------- Storage Account ----------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${appName}storage'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
}

// Round 31 (2026-05-31): blob CORS so iOS Safari can fetch SAS-signed
// audio + image blobs cross-origin. wavesurfer.js sets crossOrigin and
// fetches the audio bytes to compute waveform peaks; Safari mobile
// enforces CORS strictly for both paths. See DECISIONS.md § 22aq.
resource storageBlobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          allowedOrigins: [
            frontendOrigin
            'http://localhost:5173'
          ]
          allowedMethods: [
            'GET'
            'HEAD'
            'OPTIONS'
          ]
          allowedHeaders: [ '*' ]
          exposedHeaders: [ '*' ]
          maxAgeInSeconds: 3600
        }
      ]
    }
  }
}

// cortex-media blob container — private (SAS tokens for access, critique mitigation #3)
resource storageBlob 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/cortex-media'
  properties: { publicAccess: 'None' }
  dependsOn: [ storageBlobServices ]
}

// ---------- Outputs ----------
output storageAccountName string = storage.name
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
