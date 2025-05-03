param location string
param environmentName string
param uniqueSuffix string
param tags object

var openAiName = 'ai-${environmentName}-${uniqueSuffix}'
var speechName = 'sp-${environmentName}-${uniqueSuffix}'
param modelDeploymentName string

resource openAi 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: openAiName
  location: 'swedencentral'
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAi
  name: modelDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelDeploymentName
      version: '2025-04-14'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

resource speech 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: speechName
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: speechName
    publicNetworkAccess: 'Enabled'
  }
}

output openAiEndpoint string = openAi.properties.endpoint
output speechEndpoint string = speech.properties.endpoint
output gpt4oDeploymentName string = gpt4oDeployment.name
output openAiId string = openAi.id
output speechId string = speech.id
@secure()
output speechKey string = speech.listKeys().key1
