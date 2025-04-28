# Sample: Genesys AudioHook to Azure

A reference implementation of a WebSocket server on Azure, designed to integrate with [Genesys AudioHook protocol](https://developer.genesys.cloud/devapps/audiohook) for real-time transcription on Azure. This will implement the [AudioHook Monitor](https://help.mypurecloud.com/articles/audiohook-monitor-overview/) where the client streams audio to the server but the server does not send any results back to the client.

This AudioHook server lets you use your own speech processing pipeline—including custom speech-to-text or generative audio models—while keeping data secure and easily integrating with other cloud-native apps.

Real-time transcripts unlock advanced call center analytics, powering live summarization, agent coaching, and instant question answering to enhance customer experience and operational efficiency.


## Components

AudioHook processing is decoupled from AI services, supporting flexible deployment, robust security, and easy integration with enterprise systems. The modular design allows horizontal scaling and rapid customization of the AI pipeline for evolving contact center needs.

- [AudioHook WebSocket server (Python)](./server/python)
- Real-Time AI service (Python) (_coming soon_)

### Architecture

![Real-time architecture](./docs/images/real-time-architecture.png)
