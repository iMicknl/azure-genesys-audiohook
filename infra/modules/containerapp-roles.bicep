param containerAppPrincipalId string
param openAiId string
param speechId string
param cosmosDbAccountName string
param cosmosDbDataContributorRoleDefinitionId string
param keyVaultName string
param eventHubNamespaceName string

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

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' existing = {
  name: keyVaultName
}

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerAppPrincipalId, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2022-10-01-preview' existing = {
  name: eventHubNamespaceName
}

resource eventHubRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHubNamespace.id, containerAppPrincipalId, 'Azure Event Hubs Data Sender')
  scope: eventHubNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '761837e9-9158-4ddf-954e-7e886a4db659')
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}
