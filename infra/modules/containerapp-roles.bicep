param eventHubNamespaceName string
param eventHubName string
param containerAppPrincipalId string
param openAiId string
param speechId string
param cosmosDbAccountName string
param cosmosDbDataContributorRoleDefinitionId string

resource openAiResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: last(split(openAiId, '/'))
}

resource speechResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: last(split(speechId, '/'))
}

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' existing = {
  name: cosmosDbAccountName
}

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2022-10-01-preview' existing = {
  name: eventHubNamespaceName
}
resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2022-10-01-preview' existing = {
  name: eventHubName
  parent: eventHubNamespace
}
resource eventHubRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHub.id, containerAppPrincipalId, 'Event Hubs Data Sender')
  scope: eventHub
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'bfa99427-4437-4c20-9273-ef80fa1394b7') // Azure Event Hubs Data Sender
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Add Cosmos DB data plane role assignment

resource cosmosDbDataPlaneRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: guid(cosmosDbAccount.id, containerAppPrincipalId, cosmosDbDataContributorRoleDefinitionId)
  parent: cosmosDbAccount
  properties: {
    principalId: containerAppPrincipalId
    roleDefinitionId: cosmosDbDataContributorRoleDefinitionId
    scope: cosmosDbAccount.id
  }
}


resource openAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAiId, containerAppPrincipalId, 'Cognitive Services User')
  scope: openAiResource
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}


resource speechRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechId, containerAppPrincipalId, 'Cognitive Services Speech User')
  scope: speechResource
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f2dc8367-1007-4938-bd23-fe263f013447')
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}
