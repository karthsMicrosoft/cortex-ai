// infra/modules/container-app-job.bicep
// Round 35 — Azure Container Apps Job for the reminders dispatcher.
//
// Cron-triggered (every minute) job that runs `python -m scripts.dispatch_reminders`
// against the SAME container image as the API app. The job picks up notes whose
// due_at <= now() AND reminder_sent_at IS NULL AND done_at IS NULL, race-safely
// claims them, then fires Web Push (with email fallback). Recurring notes get
// their due_at advanced after firing.
//
// Why a Job (not APScheduler in-process): survives API restarts, no in-process
// timer drift, scales independently, matches the existing Azure-native pattern.

targetScope = 'resourceGroup'

@description('Base name prefix for resources')
param appName string

@description('Azure region for the resources')
param location string

@description('Existing Container Apps managed environment ID to host the job in')
param containerEnvId string

@description('Container image tag to run (same image as the API app)')
param containerImageTag string = 'latest'

@description('ACR login server URL')
param acrLoginServer string

@description('ACR name (registry username)')
param acrName string

@secure()
@description('ACR admin password')
param acrPassword string

@secure()
@description('Full DATABASE_URL connection string')
param databaseUrl string

@description('Azure OpenAI endpoint')
param openaiEndpoint string

@secure()
@description('Azure OpenAI API key')
param openaiApiKey string

@description('Cron expression for the job schedule. Default = every minute.')
param cronExpression string = '* * * * *'

@description('Parallelism — how many job replicas can run concurrently per trigger')
param parallelism int = 1

@description('Replica timeout in seconds — kill the job if a single run exceeds this')
param replicaTimeout int = 300

// ---------- VAPID (Web Push) ----------
// Optional: if unset, the webpush notifier no-ops gracefully and the dispatcher
// falls back to email. Documented in docs/REMINDERS.md.
@secure()
@description('VAPID public key for Web Push (optional; no-ops if unset)')
param vapidPublicKey string = ''

@secure()
@description('VAPID private key for Web Push (optional; no-ops if unset)')
param vapidPrivateKey string = ''

@description('VAPID subject (mailto: link, e.g. mailto:admin@cortex.app)')
param vapidSubject string = ''

// ---------- Azure Communication Services Email ----------
// Optional fallback channel. If unset, email notifier no-ops gracefully.
@secure()
@description('Azure Communication Services Email connection string (optional)')
param acsEmailConnection string = ''

@description('ACS Email sender address (e.g. donotreply@yourdomain.com)')
param acsEmailSender string = ''

// ---------- Container Apps Job ----------
resource remindersJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${appName}-reminders'
  location: location
  properties: {
    environmentId: containerEnvId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: replicaTimeout
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: parallelism
        replicaCompletionCount: 1
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
        { name: 'azure-openai-api-key',            value: openaiApiKey }
        { name: 'vapid-public-key',                value: vapidPublicKey }
        { name: 'vapid-private-key',               value: vapidPrivateKey }
        { name: 'acs-email-connection',            value: acsEmailConnection }
      ]
    }
    template: {
      containers: [
        {
          name: '${appName}-reminders'
          image: '${acrLoginServer}/${appName}-api:${containerImageTag}'
          command: [ 'python' ]
          args: [ '-m', 'scripts.dispatch_reminders' ]
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'DATABASE_URL',                   secretRef: 'database-url' }
            { name: 'AZURE_OPENAI_ENDPOINT',          value: openaiEndpoint }
            { name: 'AZURE_OPENAI_API_KEY',           secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_API_VERSION',       value: '2024-10-21' }
            { name: 'VAPID_PUBLIC_KEY',               secretRef: 'vapid-public-key' }
            { name: 'VAPID_PRIVATE_KEY',              secretRef: 'vapid-private-key' }
            { name: 'VAPID_SUBJECT',                  value: vapidSubject }
            { name: 'ACS_EMAIL_CONNECTION',           secretRef: 'acs-email-connection' }
            { name: 'ACS_EMAIL_SENDER',               value: acsEmailSender }
            { name: 'ENVIRONMENT',                    value: 'production' }
          ]
        }
      ]
    }
  }
}

// ---------- Outputs ----------
output remindersJobName string = remindersJob.name
output remindersJobId   string = remindersJob.id
