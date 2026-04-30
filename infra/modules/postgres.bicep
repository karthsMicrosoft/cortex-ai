// infra/modules/postgres.bicep
// PostgreSQL Flexible Server with pgvector extension and Azure firewall rule (OQ-5)
targetScope = 'resourceGroup'

@description('Base name prefix for the resource')
param appName string

@description('Azure region for the resource')
param location string

@secure()
@description('PostgreSQL admin password')
param dbAdminPassword string

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

// Enable pgvector and uuid-ossp extensions via the Azure allowlist.
// NOTE: In-DB extension name is 'vector' (lowercase); ARM allowlist token is 'VECTOR' (uppercase).
resource pgvectorExt 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'azure.extensions'
  properties: { value: 'VECTOR,UUID-OSSP', source: 'user-override' }
}

// OQ-5: Firewall rule so Azure Container Apps can reach Postgres.
// startIpAddress and endIpAddress both 0.0.0.0 is the Azure magic value for
// "Allow all Azure services and resources within Azure IPs".
resource postgresFwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------- Outputs ----------
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresName string = postgres.name
