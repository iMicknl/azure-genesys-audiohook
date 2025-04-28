targetScope = 'subscription'

@description('The location for all resources')
param location string

@description('Environment name')
param environmentName string

@description('Container image to deploy')
param containerImage string

@secure()
param websocketServerClientSecret string = base64(newGuid())

var uniqueSuffix = substring(uniqueString(subscription().id, environmentName), 0, 5)
var tags = {
  environment: environmentName
  application: 'azure-genesys-audiohook'
}
var rgName = 'rg-${environmentName}-${uniqueSuffix}'
var modelName = 'gpt-4.1-mini'

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

// Deploy container app after cognitive services and storage
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
    websocketServerApiKey: '${uniqueString(subscription().id, environmentName, 'wsapikey1')}${uniqueString(subscription().id, environmentName, 'wsapikey2')}'
    websocketServerClientSecret: websocketServerClientSecret
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
  }
}

output containerAppFqdn string = containerapp.outputs.containerAppFqdn
