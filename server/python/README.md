# Genesys AudioHook Websocket Server _(work in progress)_

The websocket server is written in Python using the Quart framework for asynchronous processing. It is designed to integrate with [Genesys AudioHook protocol](https://developer.genesys.cloud/devapps/audiohook) for real-time transcription and summarization. This server is designed to be deployed on Azure as a container.

> [!NOTE]
> This application is an example implementation and is not intended for production use. It is provided as-is and is not supported.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

Easiest is to leverage the included DevContainer configuration to get started. This will install all the necessary dependencies and tools to get started.

## Installation

You can install the dependencies via the command below using uv.

```bash
uv sync
```

## Development

You can start the development server via the command below. The server will start on port 5001 and listen for incoming websocket connections.

```bash
uv run server.py
```

During development, you can leverage the [Genesys AudioHook Sample Service](https://github.com/purecloudlabs/audiohook-reference-implementation/tree/main/client) to test the server. This client implements the Genesys AudioHook protocol and will send event and audio data to the chosen websocket server. The client can communicate with websockets over a secure connection (wss) or an insecure connection (ws). Run the command below to start the client.

```bash
npm start --uri ws://host.docker.internal:5001/ws --api-key your_api_key --client-secret your_secret --wavfile your_audio.wav
```

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
- Add support for Azure Blob Storage for saving audio files
- Add support for Azure AI Speech / Azure OpenAI Whisper for speech-to-text
- Add extensive logging frameworks
- Make application stateless
- Add retry handling and reconnect on disconnect
