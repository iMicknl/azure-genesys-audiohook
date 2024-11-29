# Sample: Genesys AudioHook to Azure

A reference implementation of a WebSocket server on Azure, designed to integrate with [Genesys AudioHook protocol](https://developer.genesys.cloud/devapps/audiohook) for real-time transcription and summarization. This will implement the [AudioHook Monitor](https://help.mypurecloud.com/articles/audiohook-monitor-overview/) where the client streams audio to the server but the server does not send any results back to the client.

- [Python WebSocket server](./server/python)

## Architecture

![Real-time architecture](./docs/images/real-time-architecture.png)
