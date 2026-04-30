// infra/modules/static-web-app.bicep
// Azure Static Web App (Free SKU) — OQ-6 resolution
// Using Microsoft.Web/staticSites so the entire stack is reproducible from Bicep
// (rather than relying solely on `az staticwebapp create` in deploy.sh).
// CI/CD wiring is handled by .github/workflows/deploy-frontend.yml.
targetScope = 'resourceGroup'

@description('Base name prefix for the resource')
param appName string

@description('Azure region for the Static Web App')
param location string

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
output staticWebAppName string = staticWebApp.name
output staticWebAppHost string = staticWebApp.properties.defaultHostname
