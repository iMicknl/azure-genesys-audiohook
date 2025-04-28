param containerAppPrincipalId string
param openAiId string
param speechId string
param cosmosDbAccountName string

resource openAiResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: last(split(openAiId, '/'))
}

resource speechResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: last(split(speechId, '/'))
}

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' existing = {
  name: cosmosDbAccountName
}

// Add Cosmos DB data plane role assignment
@description('The Cosmos DB Built-in Data Contributor data plane role definition id')
param cosmosDbDataContributorRoleDefinitionId string

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
