param location string
param environmentName string
param uniqueSuffix string
param tags object

var eventHubNamespaceName = 'evhns-${environmentName}-${uniqueSuffix}'
var eventHubName = 'evh-${environmentName}-${uniqueSuffix}'

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2022-10-01-preview' = {
  name: eventHubNamespaceName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
  properties: {
    isAutoInflateEnabled: true
    maximumThroughputUnits: 4
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2022-10-01-preview' = {
  name: '${eventHubNamespace.name}/${eventHubName}'
  properties: {
    messageRetentionInDays: 1
    partitionCount: 2
  }
}

resource eventHubAuthRule 'Microsoft.EventHub/namespaces/eventhubs/authorizationRules@2022-10-01-preview' = {
  name: '${eventHubNamespace.name}/${eventHubName}/sendListenRule'
  properties: {
    rights: [
      'Send'
      'Listen'
    ]
  }
}

output eventHubNamespaceName string = eventHubNamespace.name
output eventHubName string = eventHub.name
output eventHubConnectionString string = listKeys(eventHubAuthRule.id, '2022-10-01-preview').primaryConnectionString
