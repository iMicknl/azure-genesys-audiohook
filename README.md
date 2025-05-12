# Sample: Genesys AudioHook to Azure

This project provides a reference implementation of a WebSocket server on Azure that integrates with the [Genesys AudioHook protocol](https://developer.genesys.cloud/devapps/audiohook) for real-time transcription. It implements the [AudioHook Monitor](https://help.mypurecloud.com/articles/audiohook-monitor-overview/), where audio is streamed from the client to the server, and the server does not return results to the client.

This AudioHook server enables you to connect your own speech processing pipeline—such as Azure AI (Custom) Speech, GPT-4o Transcribe, Whisper, or other services—while maintaining data security and seamless integration with cloud-native applications.

Real-time transcription enables advanced call center analytics, such as live summarization, agent coaching, and instant question answering, to improve customer experience and operational efficiency.

> [!NOTE]
> This repository accelerates integration between Genesys Cloud and Azure for demonstration and development purposes. It is not production-ready; carefully review, test, and adapt it to meet your organization's security, compliance, and operational requirements before production deployment.

## Components

The AudioHook processing is separated from AI services, allowing flexible deployment, strong security, and straightforward integration with enterprise systems. Its modular architecture supports horizontal scaling and rapid customization of the AI pipeline to meet evolving contact center requirements.

- [AudioHook WebSocket server (Python)](./server/python)
- Real-time AI processing service (Python, Semantic Kernel) (_coming soon_)
- Demo front-end (JavaScript, React) with back-end (Python) (_coming soon_)

### Architecture

![Real-time architecture](./docs/images/real-time-architecture.png)

## Deployment

Deploy this accelerator using the provided [infrastructure-as-code (Bicep)](./infra) templates. The recommended method is the [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/), which simplifies authentication, resource provisioning, and configuration.

1. Authenticate with Azure by running:

    ```bash
    azd auth login
    ```

    This opens a browser window for secure sign-in.

1. Create a new environment with:

    ```bash
    azd env new
    ```

1. (optional) At this stage, you can customize your deployment by setting environment variables. You can configure the following settings:

    ```bash
        azd env set SPEECH_PROVIDER <option>
        azd env set AZURE_SPEECH_LANG <locale(s)>
    ```

    | Parameter           | Default              | Options / Description                                                                                                                                                                                                                 |
    |---------------------|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
    | `SPEECH_PROVIDER`   | `azure-ai-speech`    | Choose the speech-to-text provider:`azure-ai-speech` or `azure-openai-gpt4o-transcribe`.   |
    | `AZURE_SPEECH_LANG` | `en-US`              | Specify one or more supported locales (comma-separated, e.g. `en-US,nl-NL`). See the [full list of supported languages](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt). When multiple locales are set, automatic language identification is enabled. |

1. Deploy resources with:

    ```bash
    azd up
    ```

1. During deployment, you’ll be prompted for:

    | Parameter           | Description                                                                  |
    |---------------------|------------------------------------------------------------------------------|
    | Azure Subscription  | The Azure subscription for resource deployment.                              |
    | Azure Location      | The Azure region for resources                                               |
    | Environment Name    | A unique environment name (used as a prefix for resource names).             |

    For best compatibility, use `swedencentral` as your Azure region. Other regions may not be fully supported or tested.

1. After deployment, the CLI will display a link to your web service. Open it in your browser, you should see `{"status": "healthy"}` to confirm the service is running.


> [!IMPORTANT]
> The default infrastructure templates use public networking. For production, secure your deployment with Azure Front Door, Azure Web Application Firewall (WAF), or restrict access to [Genesys Cloud IP ranges](https://help.mypurecloud.com/faqs/obtain-the-ip-address-range-for-my-region-for-audiohook/), as Genesys Cloud requires a publicly accessible endpoint.


## Configure Genesys Cloud AudioHook

Once your web service is running, configure the AudioHook Monitor in Genesys Cloud to stream audio to your Azure deployment.

1. Follow the [Genesys configuration guide](https://help.mypurecloud.com/articles/configure-and-activate-audiohook-monitor-in-genesys-cloud/).

2. Use the Connection URI output after deployment, or take the web service URL from step 4, replace `https` with `wss`, and append `/audiohook/ws` as the path.

3. Select the **Credentials** tab. Here, you must provide the API Key and Client Secret. In the Azure Portal, go to your deployed resource group and open the Key Vault. Under **Objects > Secrets**, locate the API Key and Client Secret.

    These secrets are generated automatically during deployment, but for security, it is recommended to update them with your own values. Ensure the Client Secret is a BASE64-encoded string.

> [!NOTE]
> If you cannot view the secrets, go to **Access control (IAM)** in the Key Vault and assign yourself the **Key Vault Secrets Officer** role.

4. Activate your AudioHook.

### Test your deployment

1. Place a call to your Genesys queue where the AudioHook Monitor is enabled.

2. Open your deployed web service in a browser. The following endpoints are available to check conversation status:

    ```
    /api/conversations?key={API_KEY}&active=false|true
    /api/conversation/{CONVERSATION_ID}?key={API_KEY}
    ```

3. Confirm that the call audio is being transcribed as expected.

## Clean up resources

When you no longer need the resources created in this article, run the following command to power down the app:

```bash
azd down
```

If you want to redeploy to a different region, delete the `.azure` directory before running `azd up` again. In a more advanced scenario, you could selectively edit files within the `.azure` directory to change the region.
