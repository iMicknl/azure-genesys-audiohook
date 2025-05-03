param location string
param environmentName string
param uniqueSuffix string
param tags object
@secure()
param speechKey string

var keyVaultName = toLower(replace('kv-${environmentName}-${uniqueSuffix}', '_', '-'))
var sanitizedKeyVaultName = take(toLower(replace(replace(replace(replace(keyVaultName, '--', '-'), '_', '-'), '[^a-zA-Z0-9-]', ''), '-$', '')), 24)

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: sanitizedKeyVaultName
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

resource speechKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'azure-speech-key'
  properties: {
    value: speechKey
  }
}

var keyVaultDnsSuffix = environment().suffixes.keyvaultDns

output apiKeySecretUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${apiKeySecret.name}'
output clientSecretUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${clientSecret.name}'
output speechKeySecretUri string = 'https://${keyVault.name}${keyVaultDnsSuffix}/secrets/${speechKeySecret.name}'
output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
