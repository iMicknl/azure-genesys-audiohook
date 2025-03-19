# Genesys AudioHook Websocket Server _(work in progress)_

The websocket server, built with the Quart framework, integrates with the [Genesys AudioHook protocol](https://developer.genesys.cloud/devapps/audiohook) for real-time transcription. It is designed for deployment on Azure as a container, connecting to various Azure services, including Azure AI Speech for transcription, Azure Event Hub for event streaming, and Azure Blob Storage for storing audio files.

> [!NOTE]
> This application is an example implementation and is not intended for production use. It is provided as-is and is not supported.

## Prerequisites

The easiest way to get started is by using the included DevContainer configuration. This setup will install all necessary dependencies and tools automatically.

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Azure resources

- Azure Event Hub
- Azure Blob Storage
- Azure AI Speech

## Installation

You can install the dependencies via the command below using uv.

```bash
uv sync
```

## Development

Start the development server with the command below. It will run on port 5001, listening for websocket connections. The server will automatically restart on code changes.

```bash
uv run server.py
```

During development, you can use the [Genesys AudioHook Sample Service](https://github.com/purecloudlabs/audiohook-reference-implementation/tree/main/client) to test the server. This client implements the Genesys AudioHook protocol and sends event and audio data to the websocket server. It supports both secure (wss) and insecure (ws) connections. Run the command below to start the client, ensuring the API key and secret match your environment variables.

```bash
cd client
npm install
```
If you are using devcontainers, and your service is being served in localhost, make sure that you firewall rules for WSL are correctly setup (in your Windows Host):
```
sudo New-NetFirewallRule -DisplayName "WSL" -Direction Inbound  -InterfaceAlias "vEthernet (WSL (Hyper-V firewall))"  -Action Allow
sudo New-NetFirewallRule -DisplayName "Allow Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```
Also, if you are using WSL, which would be your case if you are using devcontainers in windows, make sure to mirror your networking in wsl by creating a ~/.wslconfig with the following (in your Windows home location):

```
[wsl2]
networkingMode=mirrored
```

Then you can start your client: 
```bash
npm start --uri ws://host.docker.internal:5000/ws --api-key your_api_key --client-secret your_secret --wavfile your_audio.wav

OR 
npm start -- --uri ws://localhost:5000/ws --api-key your_api_key --client-secret  your_secret --wavfile output_8k-stereo.wav
```

Example:
```bash
cd client
npm start -- --uri wss://audiohook.example.com/api/v1/audiohook/ws --api-key SGVsbG8sIEkgYW0gdGhlIEFQSSBrZXkh --client-secret TXlTdXBlclNlY3JldEtleVRlbGxOby0xITJAMyM0JDU= --wavfile output_8k-stereo.wav
```

To perform a load test on your websocket server, use the `--session-count` parameter to set the number of concurrent sessions.

### Tests

You can run the tests via the command below. The tests are written using the Pytest framework.

```bash
uv run pytest tests
```

## Production

In production, it is recommended to use a production-grade web server like Gunicorn /w Uvicorn workers to serve the application. This will allow for better performance and scalability. You can leverage the included Dockerfile or leverage the command below to start the server.

```
gunicorn server:app
```

### Deploy to Azure

This repository doesn't provide an infrastructure as code (IaC) solution for deploying the server to Azure. However, you can leverage the Azure CLI to deploy the server to Azure Container Apps. Run the command below to deploy the server to Azure Container Apps.

```bash
az containerapp up --resource-group your-resource-group \
--name your-application-name - --location westeurope \
--ingress external --target-port 8000 --source . \
--env-vars WEBSOCKET_SERVER_API_KEY="your_api_key" WEBSOCKET_SERVER_CLIENT_SECRET="your_secret=" DEBUG_MODE="true"
```

## TODO
- Add extensive logging frameworks
- Make application stateless
- Add retry handling and reconnect on disconnect
- Benchmarks and performance testing, optimize for performance
