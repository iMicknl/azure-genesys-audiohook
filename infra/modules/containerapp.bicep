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

var containerAppName = 'ca-${environmentName}-${uniqueSuffix}'
var containerEnvName = 'cae-${environmentName}-${uniqueSuffix}'
var logAnalyticsName = 'log-${environmentName}-${uniqueSuffix}'

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
              value: 'westeurope'
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
          ]
          resources: {
            cpu: json('2.0')
            memory: '4.0Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
      }
    }
  }
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppPrincipalId string = containerApp.identity.principalId
