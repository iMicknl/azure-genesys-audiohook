param location string
param environmentName string
param uniqueSuffix string
param tags object
param containerImage string
param openAiEndpoint string
param speechResourceId string
param modelDeploymentName string
param cosmosDbEndpoint string
param cosmosDbDatabase string
param cosmosDbContainer string
@secure()
param websocketServerApiKey string
@secure()
param websocketServerClientSecret string
param speechRegion string

// Helper to sanitize environmentName for valid container app name
var sanitizedEnvName = toLower(replace(replace(replace(replace(environmentName, ' ', '-'), '--', '-'), '[^a-zA-Z0-9-]', ''), '_', '-'))
var containerAppName = take('ca-${sanitizedEnvName}-${uniqueSuffix}', 32)
var containerEnvName = take('cae-${sanitizedEnvName}-${uniqueSuffix}', 32)
var logAnalyticsName = take('log-${sanitizedEnvName}-${uniqueSuffix}', 63)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-10-02-preview' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
      }
    }
    template: {
      containers: [
        {
          name: containerAppName
          image: containerImage
          env: [
            {
              name: 'AZURE_SPEECH_LANGUAGES'
              value: 'en-US'
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_MODEL_DEPLOYMENT'
              value: modelDeploymentName
            }
            {
              name: 'AZURE_SPEECH_RESOURCE_ID'
              value: speechResourceId
            }
            {
              name: 'AZURE_SPEECH_REGION'
              value: speechRegion
            }
            {
              name: 'AZURE_COSMOSDB_ENDPOINT'
              value: cosmosDbEndpoint
            }
            {
              name: 'AZURE_COSMOSDB_DATABASE'
              value: cosmosDbDatabase
            }
            {
              name: 'AZURE_COSMOSDB_CONTAINER'
              value: cosmosDbContainer
            }
            {
              name: 'WEBSOCKET_SERVER_API_KEY'
              value: websocketServerApiKey
            }
            {
              name: 'WEBSOCKET_SERVER_CLIENT_SECRET'
              value: websocketServerClientSecret
            }
            {
              name: 'DEBUG_MODE'
              value: 'true'
            }
          ]
          resources: {
            cpu: json('2.0')
            memory: '4.0Gi'
          }
        }
      ]
      // TODO add memory/cpu scaling
      scale: {
        minReplicas: 1
        maxReplicas: 10
        rules: [
          {
            name: 'http-scaler'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppPrincipalId string = containerApp.identity.principalId
