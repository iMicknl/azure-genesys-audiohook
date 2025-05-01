param location string
param environmentName string
param uniqueSuffix string
param tags object

var keyVaultName = toLower(replace('kv-${environmentName}-${uniqueSuffix}', '_', '-'))

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    accessPolicies: []
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}


@secure()
param websocketServerApiKey string = ''

resource apiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'websocket-server-api-key'
  properties: {
    value: websocketServerApiKey
  }
}



@secure()
param websocketServerClientSecret string = ''

resource clientSecret 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'websocket-server-client-secret'
  properties: {
    value: websocketServerClientSecret
  }
}


output clientSecretUri string = '${keyVault.id}/secrets/websocket-server-client-secret'
output apiKeySecretUri string = '${keyVault.id}/secrets/websocket-server-api-key'
