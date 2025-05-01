targetScope = 'subscription'

@description('The location for all resources')
param location string

@description('Environment name')
param environmentName string

@description('Container image to deploy')
param containerImage string

@description('Comma-separated list of Azure Speech languages, e.g. "en-US,nl-NL"')
param azureSpeechLanguages string = 'en-US'

var uniqueSuffix = substring(uniqueString(subscription().id, environmentName), 0, 5)
var tags = {
  environment: environmentName
  application: 'azure-genesys-audiohook'
}
var rgName = 'rg-${environmentName}-${uniqueSuffix}'


var modelName = 'gpt-4.1-mini'


// Deploy Key Vault and secrets
module keyvault 'modules/keyvault.bicep' = {
  scope: rg
  name: 'keyvault-deployment'
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
    websocketServerApiKey: '${uniqueString(subscription().id, environmentName, 'wsapikey')}${uniqueString(subscription().id, environmentName, 'wsapikey2')}'
    websocketServerClientSecret: base64(uniqueString(subscription().id, environmentName, 'wsclientsecret'))
  }
}

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: rgName
  location: location
  tags: tags
}

module cognitive 'modules/cognitive.bicep' = {
  scope: rg
  name: 'cognitive-deployment'
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
    modelDeploymentName: modelName
  }
}

module cosmosdb 'modules/cosmosdb.bicep' = {
  scope: rg
  name: 'cosmosdb-deployment'
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
  }
}

// Deploy container app after cognitive services, storage, and key vault
module containerapp 'modules/containerapp.bicep' = {
  scope: rg
  name: 'containerapp-deployment'
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
    containerImage: containerImage
    openAiEndpoint: cognitive.outputs.openAiEndpoint
    speechResourceId: cognitive.outputs.speechId
    modelDeploymentName: modelName
    cosmosDbEndpoint: cosmosdb.outputs.cosmosDbAccountEndpoint
    cosmosDbDatabase: cosmosdb.outputs.cosmosDbDatabaseName
    cosmosDbContainer: cosmosdb.outputs.cosmosDbContainerName
    apiKeySecretUri: keyvault.outputs.apiKeySecretUri
    clientSecretUri: keyvault.outputs.clientSecretUri
    speechRegion: location
    azureSpeechLanguages: azureSpeechLanguages
  }
}

// Add role assignments for the container app's system-assigned identity
module containerAppRoleAssignments 'modules/containerapp-roles.bicep' = {
  scope: rg
  name: 'containerapp-role-assignments'
  params: {
    containerAppPrincipalId: containerapp.outputs.containerAppPrincipalId
    openAiId: cognitive.outputs.openAiId
    speechId: cognitive.outputs.speechId
    cosmosDbAccountName: cosmosdb.outputs.cosmosDbAccountName
    cosmosDbDataContributorRoleDefinitionId: cosmosdb.outputs.cosmosDbDataContributorRoleDefinitionId
    keyVaultName: keyvault.outputs.keyVaultName
  }
}

output containerAppFqdn string = containerapp.outputs.containerAppFqdn
output audioHookConnectionUri string = 'wss://${containerapp.outputs.containerAppFqdn}/audiohook/ws'
