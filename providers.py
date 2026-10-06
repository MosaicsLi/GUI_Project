# providers.py - LLM providers (HTTP without SDK, and official SDKs)
#
# PLACEHOLDER: this file is not implemented yet.
#
# Assignment requirements planned for this file:
#   [REQ: if-else]     create_provider()
#   [REQ: for]         GoogleSdkProvider.convert_messages(), load_providers()
#   [REQ: range]       ChatProvider.chat()
#   [REQ: list/dict]   PROVIDER_LIST, messages, payload, headers
#   [REQ: class]       ChatProvider -> HttpProvider / SdkProvider -> 5 subclasses
#   [REQ: exception]   HttpProvider.send(), SdkProvider.get_client()
#   [REQ: module]      json, re, os, time, urllib
#
# Planned classes:
#   ChatProvider
#   |-- HttpProvider            (no SDK, OpenAI format)
#   |   |-- LMStudioProvider
#   |   `-- OllamaProvider
#   `-- SdkProvider             (official SDK)
#       |-- GoogleSdkProvider
#       |-- ClaudeSdkProvider
#       `-- OpenAISdkProvider
#
# Planned functions:
#   create_provider(info)  - build one provider object from one item of PROVIDER_LIST
#   load_providers()       - return {"HTTP": [...], "SDK": [...]}
