# Genesys AudioHook Websocket Server _(work in progress)_

The websocket server, built with the Quart framework, integrates with the [Genesys AudioHook protocol](https://developer.genesys.cloud/devapps/audiohook) for real-time transcription. It is designed for deployment on Azure as a container, connecting to various Azure services, including Azure AI Speech for transcription, Azure Event Hub for event streaming, and Azure Blob Storage for storing audio files.

> [!NOTE]
> This application is an example implementation and is not intended for production use. It is provided as-is and is not supported.

## Prerequisites

The easiest way to get started is by using the included DevContainer configuration. This setup will install all necessary dependencies and tools automatically.

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Azure resources

- Azure AI Speech
- Azure Cosmos DB
- Azure Event Hub (optional)
- Azure Blob Storage (optional)

## Installation

You can install the dependencies via the command below using uv.

```bash
uv sync
```

## Development

Copy the `.env.sample` file to `.env`:

```bash
cp .env.sample .env
```

Edit the `.env` file to provide your own configuration values. The `.env.sample` file contains example environment variables required to run the server. These variables are loaded automatically when the server starts.

Start the development server with the command below. It will run on port 5001, listening for websocket connections. The server will automatically restart on code changes.

```bash
uv run server.py
```

### Integration test

During development, you can use the [Genesys AudioHook Sample Service](https://github.com/purecloudlabs/audiohook-reference-implementation/tree/main/client) to test the server. This client implements the Genesys AudioHook protocol and sends event and audio data to the websocket server. It supports both secure (wss) and insecure (ws) connections. Run the command below to start the client, ensuring the API key and secret match your environment variables.

```bash
git clone https://github.com/purecloudlabs/audiohook-reference-implementation.git
cd client
npm install
```

> [!NOTE]
> If running the Genesys client on Windows while the server is in a DevContainer (WSL), ensure WSL allows inbound traffic. Run these PowerShell commands as administrator:
>
> ```powershell
> New-NetFirewallRule -DisplayName "WSL" -Direction Inbound -InterfaceAlias "vEthernet (WSL (Hyper-V firewall))" -Action Allow
> New-NetFirewallRule -DisplayName "Allow Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
> ```
>
> If you encounter connectivity issues, try using [Mirrored mode networking](https://learn.microsoft.com/en-us/windows/wsl/networking#mirrored-mode-networking) as an alternative solution.


Then you can start your client:
```bash
npm start --uri ws://host.docker.internal:5000/audiohook/ws --api-key your_api_key --client-secret your_secret --wavfile your_audio.wav
```
OR
```bash
npm start -- --uri ws://localhost:5000/audiohook/ws --api-key your_api_key --client-secret  your_secret --wavfile your_audio.wav
```

To perform a load test on your websocket server, use the `--session-count` parameter to set the number of concurrent sessions.

> [!WARNING]
> Ensure your audio (.wav) uses 8000Hz sample rate, U-Law encoding, and preferably stereo channels (customer/agent split). Use tools like Audacity for conversion.

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

This repository doesn't provide an infrastructure as code (IaC) solution for deploying the server to Azure yet. However, you can leverage the Azure CLI to deploy the server to Azure Container Apps. Run the command below to deploy the server to Azure Container Apps.

You will need to seperately deploy additional services (e.g. Azure AI Speech, Azure CosmosDB) and add them to your environment variables during deployment.

```bash
az containerapp up --resource-group your-resource-group \
--name your-application-name - --location westeurope \
--ingress external --target-port 8000 --source . \
--env-vars WEBSOCKET_SERVER_API_KEY="your_api_key" WEBSOCKET_SERVER_CLIENT_SECRET="your_secret=" DEBUG_MODE="true"
```
