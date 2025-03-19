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

## Configuration
The `.env.sample` file contains definitions that are required for setting up the server and the connection to the Azure services. Make sure  to replace the entries with your own entries. 

## Development

You can start the development server via the command below. The server will start on port 5001 and listen for incoming websocket connections.

```bash
uv run server.py
```

During development, you can leverage the [Genesys AudioHook Sample Service](https://github.com/purecloudlabs/audiohook-reference-implementation/tree/main/client) to test the server. This client implements the Genesys AudioHook protocol and will send event and audio data to the chosen websocket server. The client can communicate with websockets over a secure connection (wss) or an insecure connection (ws). Run the command below to start the client. (It is recommended to `npm install` from the client folder only to avoid the installation of unncessary packages that could also conflict.)

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
