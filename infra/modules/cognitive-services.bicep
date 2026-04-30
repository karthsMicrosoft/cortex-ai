// infra/modules/cognitive-services.bicep
// Azure OpenAI (in openaiLocation per OQ-1), Azure Speech S0, Azure AI Vision S1
targetScope = 'resourceGroup'

@description('Base name prefix for resources')
param appName string

@description('Azure region for Speech and Vision resources')
param location string

@description('Azure OpenAI region — gpt-4o-mini and text-embedding-3-small are not GA in westus2. OQ-1 resolution.')
param openaiLocation string = 'westus'

// ---------- Azure OpenAI (OQ-1: must be in openaiLocation, NOT westus2) ----------
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

// ---------- Azure AI Vision (ComputerVision S1) ----------
resource vision 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-vision'
  location: location
  kind: 'ComputerVision'
  sku: { name: 'S1' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Outputs ----------
output openaiEndpoint  string = openai.properties.endpoint
output openaiKey       string = openai.listKeys().key1
output openaiRegion    string = openaiLocation
output speechKey       string = speech.listKeys().key1
output speechRegion    string = location
output visionEndpoint  string = vision.properties.endpoint
output visionKey       string = vision.listKeys().key1
