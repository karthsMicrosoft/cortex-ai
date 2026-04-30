// infra/modules/storage.bicep
// Azure Storage Account (StorageV2 LRS) + cortex-media blob container
targetScope = 'resourceGroup'

@description('Base name prefix for the resource')
param appName string

@description('Azure region for the resource')
param location string

// ---------- Storage Account ----------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${appName}storage'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
}

// cortex-media blob container — private (SAS tokens for access, critique mitigation #3)
resource storageBlob 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/cortex-media'
  properties: { publicAccess: 'None' }
}

// ---------- Outputs ----------
output storageAccountName string = storage.name
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
