# providers.py - LLM providers (HTTP without SDK, and official SDKs)
#
# PLACEHOLDER: this file is not implemented yet.
#
# A provider only uses the values given to its constructor (URL, model, API key).
# These values come from the fields of the GUI. Nothing is hard-coded here
# except the default URL of each self-hosted server.
#
# Assignment requirements planned for this file:
#   [REQ: if-else]     create_provider(), check_settings()
#   [REQ: for]         GoogleSdkProvider.convert_messages(), get_provider_names()
#   [REQ: range]       ChatProvider.chat()
#   [REQ: list/dict]   PROVIDER_LIST, messages, payload, headers
#   [REQ: class]       ChatProvider -> HttpProvider / SdkProvider -> 5 subclasses
#   [REQ: exception]   HttpProvider.send(), SdkProvider.get_client()
#   [REQ: module]      json, re, time, urllib
#
# Planned classes:
#   ChatProvider
#   |-- HttpProvider            (no SDK, OpenAI format, also used for "Custom URL")
#   |   |-- LMStudioProvider
#   |   `-- OllamaProvider
#   `-- SdkProvider             (official SDK)
#       |-- GoogleSdkProvider
#       |-- ClaudeSdkProvider
#       `-- OpenAISdkProvider
#
# Planned module-level items:
#   PROVIDER_LIST                                    - list of dict, one dict per provider
#   create_provider(info, base_url, model, api_key)  - build one provider object
#   get_provider_names(method)                       - names shown in the second drop-down menu
