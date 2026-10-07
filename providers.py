# providers.py - LLM providers (HTTP without SDK, and official SDKs)
#
# A provider only uses the values given to its constructor (URL, model, API key).
# These values come from the fields of the GUI. Nothing is hard-coded here
# except the default URL of each self-hosted server.
#
# Assignment requirements covered in this file:
#   [REQ: if-else]     check_settings(), HttpProvider.send(), create_provider()
#   [REQ: for]         list_models(), split_system(), convert_messages(), get_provider_names()
#   [REQ: range]       ChatProvider.chat()
#   [REQ: list/dict]   PROVIDER_LIST, messages, payload, headers
#   [REQ: class]       ChatProvider -> HttpProvider / SdkProvider -> 5 subclasses
#   [REQ: exception]   ChatProvider.chat(), HttpProvider.send(), SdkProvider.get_client(),
#                      SdkProvider.call_api()
#   [REQ: module]      json, re, time, urllib
#
# Classes:
#   ChatProvider
#   |-- HttpProvider            (no SDK, OpenAI format, also used for "Custom URL")
#   |   |-- LMStudioProvider
#   |   `-- OllamaProvider
#   `-- SdkProvider             (official SDK)
#       |-- GoogleSdkProvider
#       |-- ClaudeSdkProvider
#       `-- OpenAISdkProvider
#
# Module-level items (at the end of the file):
#   METHOD_LIST                                      - the two ways to call an LLM
#   PROVIDER_LIST                                    - list of dict, one dict per provider
#   get_provider_names(method)                       - names shown in the second drop-down menu
#   find_provider_info(name)                         - the dict of one provider
#   create_provider(info, base_url, model, api_key)  - build one provider object

import json
import re
import time
import urllib.error
import urllib.request

from errors import BadResponseError, ConnectionFailedError, InvalidSettingError
from errors import LLMError, MissingKeyError, SdkMissingError

# Seconds to wait before trying again after a failed connection.
RETRY_WAIT = 1

# Some local models write their thinking between <think> and </think>.
THINK_PATTERN = r"<think>.*?</think>"

# A Base URL has to start with http:// or https://
URL_PATTERN = r"^https?://\S+$"


def is_retry_status(status_code):
    """Return True when trying again may fix an HTTP error with this status code.

    5xx: the server had a problem.  429: too many requests, wait and try again.
    Other codes (401 wrong key, 404 wrong model name) will not fix themselves.
    """
    return status_code >= 500 or status_code == 429


# [REQ: class] Parent class of every provider.
class ChatProvider:
    """Parent class of every LLM provider.

    A subclass only has to write call_api(). The shared steps
    (check the settings, retry, clean the reply) are written here once.
    """

    # True when the provider cannot work without an API key.
    NEEDS_KEY = True

    def __init__(self, name, model, api_key="", timeout=60, max_retries=2):
        # name: name shown in the GUI, for example "LM Studio"
        self.name = name
        # model: name of the model, typed by the user
        self.model = model.strip()
        # api_key: typed by the user, may be empty for a self-hosted server
        self.api_key = api_key.strip()
        # timeout: seconds to wait for a reply
        self.timeout = timeout
        # max_retries: how many times to try, at least 1
        self.max_retries = max(1, max_retries)

    def check_settings(self):
        """Raise an error when a setting typed by the user is missing."""
        # [REQ: if-else] Stop early with a clear message instead of a confusing network error.
        if self.model == "":
            raise InvalidSettingError("Model", "Please type the name of the model.")
        if self.NEEDS_KEY and self.api_key == "":
            raise MissingKeyError(self.name)

    def call_api(self, messages):
        """Call the API one time and return the text of the reply.

        Every subclass has to write this method.
        """
        raise NotImplementedError

    def chat(self, messages):
        """Send the messages and return the reply. This is the method the GUI calls.

        messages uses the OpenAI format, a list of dict:
            [{"role": "user", "content": "Hello"}, ...]
        """
        self.check_settings()

        # [REQ: range] [REQ: exception] Try up to max_retries times before giving up.
        for attempt in range(self.max_retries):
            try:
                reply = self.call_api(messages)
                return self.clean_reply(reply)
            except ConnectionFailedError as error:
                is_last_try = (attempt == self.max_retries - 1)
                # [REQ: if-else] Give up on the last try, or when trying again is
                # useless (a wrong key or a wrong model name will not fix itself).
                # "raise" alone sends the same error on to the caller.
                if is_last_try or not error.can_retry:
                    raise
                else:
                    time.sleep(RETRY_WAIT)

    def clean_reply(self, text):
        """Remove the <think>...</think> part and the spaces around the reply."""
        # [REQ: module] re.DOTALL lets "." also match a new line.
        text = re.sub(THINK_PATTERN, "", text, flags=re.DOTALL)
        text = text.strip()
        if text == "":
            raise BadResponseError("The reply from " + self.name + " is empty.")
        return text


# [REQ: class] HttpProvider inherits from ChatProvider.
# It adds its own attribute (base_url) and its own methods (build_request, send, ...).
class HttpProvider(ChatProvider):
    """Call an OpenAI-format server with urllib, without any SDK.

    Used for self-hosted LLM servers. This class itself is the "Custom URL" choice.
    """

    # A self-hosted server usually has no API key.
    NEEDS_KEY = False
    # URL filled in the GUI when the user has not typed one yet.
    DEFAULT_URL = ""

    def __init__(self, name, base_url, model, api_key="", timeout=60, max_retries=2):
        super().__init__(name, model, api_key, timeout, max_retries)
        # base_url: for example "http://localhost:1234/v1", typed by the user
        self.base_url = base_url.strip().rstrip("/")

    def check_url(self):
        """Raise an error when the Base URL is empty or does not look like a URL."""
        # [REQ: module] [REQ: if-else] re checks that the URL starts with http:// or https://
        if re.match(URL_PATTERN, self.base_url) is None:
            raise InvalidSettingError("Base URL", "It has to start with http:// or https://")

    def check_settings(self):
        """Check the Base URL, then do the checks of the parent class."""
        self.check_url()
        super().check_settings()

    def build_headers(self):
        """Return the HTTP headers as a dict."""
        # [REQ: list/dict] Headers are a dict of name -> value.
        headers = {"Content-Type": "application/json"}
        # [REQ: if-else] Only send the key when the user typed one.
        if self.api_key != "":
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def build_request(self, messages):
        """Return the URL, the headers and the payload of a chat request."""
        url = self.base_url + "/chat/completions"
        # [REQ: list/dict] The payload is a dict, and messages inside it is a list of dict.
        payload = {"model": self.model, "messages": messages}
        return url, self.build_headers(), payload

    def send(self, url, headers, payload=None):
        """Send one HTTP request and return the JSON reply as a dict.

        With a payload it is a POST request, without a payload it is a GET request.
        """
        # [REQ: if-else] [REQ: module] json.dumps turns the dict into text for the request body.
        if payload is None:
            request = urllib.request.Request(url, headers=headers, method="GET")
        else:
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")

        # [REQ: exception] Turn every network problem into our own error classes.
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            # The server answered, but with an error code such as 401 or 500.
            detail = error.read().decode("utf-8", errors="replace")[:200]
            message = self.name + " returned HTTP " + str(error.code) + ": " + detail
            raise ConnectionFailedError(message, can_retry=is_retry_status(error.code))
        except (OSError, ValueError) as error:
            # OSError: cannot connect or timeout.  ValueError: the URL is not valid.
            raise ConnectionFailedError("Cannot connect to " + self.name + ": " + str(error))

        # [REQ: exception] [REQ: module] json.loads turns the text back into a dict.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise BadResponseError("The reply from " + self.name + " is not JSON.")

    def parse_response(self, data):
        """Take the text of the reply out of the dict returned by the server."""
        # [REQ: exception] The reply may not have the keys that we expect.
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise BadResponseError("The reply from " + self.name + " has an unexpected format.")

        if not isinstance(content, str):
            raise BadResponseError("The reply from " + self.name + " has no text.")
        return content

    def call_api(self, messages):
        """Call /chat/completions one time and return the text of the reply."""
        url, headers, payload = self.build_request(messages)
        data = self.send(url, headers, payload)
        return self.parse_response(data)

    def list_models(self):
        """Ask the server which models it has and return their names as a list."""
        self.check_url()
        data = self.send(self.base_url + "/models", self.build_headers())

        # [REQ: list/dict] [REQ: for] [REQ: exception] Collect the "id" of every model.
        names = []
        try:
            for item in data["data"]:
                names.append(item["id"])
        except (KeyError, TypeError):
            raise BadResponseError("The model list from " + self.name + " has an unexpected format.")
        return names


# [REQ: class] LMStudioProvider inherits from HttpProvider.
class LMStudioProvider(HttpProvider):
    """LM Studio server. It uses the OpenAI format, so only the default URL is different."""

    DEFAULT_URL = "http://localhost:1234/v1"


# [REQ: class] OllamaProvider inherits from HttpProvider.
# It has its own method (get_native_url) and its own version of list_models().
class OllamaProvider(HttpProvider):
    """Ollama server. Chat uses the OpenAI format, the model list uses Ollama's own API."""

    DEFAULT_URL = "http://localhost:11434/v1"

    def get_native_url(self):
        """Return the URL of Ollama's own API: the Base URL without the "/v1" at the end."""
        # [REQ: if-else]
        if self.base_url.endswith("/v1"):
            return self.base_url[:-3]
        else:
            return self.base_url

    def list_models(self):
        """Return the names of the models installed in Ollama (GET /api/tags)."""
        self.check_url()
        data = self.send(self.get_native_url() + "/api/tags", self.build_headers())

        # [REQ: list/dict] [REQ: for] [REQ: exception] Collect the "name" of every model.
        names = []
        try:
            for item in data["models"]:
                names.append(item["name"])
        except (KeyError, TypeError):
            raise BadResponseError("The model list from " + self.name + " has an unexpected format.")
        return names


# [REQ: class] SdkProvider inherits from ChatProvider.
# It adds its own attribute (client) and its own methods (get_client, split_system, ...).
class SdkProvider(ChatProvider):
    """Parent class of the providers that use an official SDK.

    A subclass has to write create_client() and ask_sdk().
    The SDK is imported inside create_client(), not at the top of this file,
    so the program still starts when an SDK is not installed.
    """

    # Name of the package to install with pip.
    SDK_NAME = ""
    # Name of the attribute that holds the HTTP status code in the SDK's error objects.
    STATUS_ATTR = "status_code"

    def __init__(self, name, model, api_key="", timeout=60, max_retries=2):
        super().__init__(name, model, api_key, timeout, max_retries)
        # client: the object of the SDK that talks to the API, created at the first use
        self.client = None

    def create_client(self):
        """Import the SDK and return its client object. Every subclass has to write this."""
        raise NotImplementedError

    def ask_sdk(self, client, messages):
        """Call the SDK one time and return the text. Every subclass has to write this."""
        raise NotImplementedError

    def get_client(self):
        """Return the client, and create it first when it does not exist yet."""
        # [REQ: if-else] [REQ: exception] ImportError means the SDK is not installed.
        if self.client is None:
            try:
                self.client = self.create_client()
            except ImportError:
                raise SdkMissingError(self.SDK_NAME)
        return self.client

    def split_system(self, messages):
        """Split the messages into the system text and the list of other messages.

        Google and Claude do not accept a "system" message inside the list,
        they want the system text as a separate setting.
        """
        system_text = ""
        others = []
        # [REQ: for] [REQ: if-else] [REQ: list/dict] Each message is a dict with "role" and "content".
        for message in messages:
            if message["role"] == "system":
                system_text = system_text + message["content"] + "\n"
            else:
                others.append(message)
        return system_text.strip(), others

    def call_api(self, messages):
        """Call the SDK one time and turn its errors into our own error classes."""
        client = self.get_client()

        # [REQ: exception] Each SDK has its own error classes. We catch them all here
        # and look at the HTTP status code to decide what kind of problem it is.
        try:
            return self.ask_sdk(client, messages)
        except LLMError:
            # Already one of our own errors, send it on unchanged.
            raise
        except Exception as error:
            # getattr reads an attribute by its name, and returns None when it does not exist.
            status_code = getattr(error, self.STATUS_ATTR, None)
            detail = str(error)[:300]
            # [REQ: if-else] No status code means the request never got an answer.
            if isinstance(status_code, int):
                message = self.name + " returned HTTP " + str(status_code) + ": " + detail
                raise ConnectionFailedError(message, can_retry=is_retry_status(status_code))
            else:
                raise ConnectionFailedError("Cannot connect to " + self.name + ": " + detail)


# [REQ: class] GoogleSdkProvider inherits from SdkProvider.
# It has its own method (convert_messages).
class GoogleSdkProvider(SdkProvider):
    """Google Gemini, using the google-genai SDK."""

    SDK_NAME = "google-genai"
    # The errors of this SDK keep the status code in "code".
    STATUS_ATTR = "code"

    def create_client(self):
        """Import the Google SDK and return its client."""
        from google import genai

        # This SDK counts the timeout in milliseconds.
        return genai.Client(api_key=self.api_key, http_options={"timeout": self.timeout * 1000})

    def convert_messages(self, messages):
        """Change messages from the OpenAI format to the format of Gemini.

        OpenAI:  {"role": "assistant", "content": "Hi"}
        Gemini:  {"role": "model", "parts": [{"text": "Hi"}]}
        """
        contents = []
        # [REQ: for] [REQ: if-else] [REQ: list/dict] Build a new list of dict, one per message.
        for message in messages:
            if message["role"] == "assistant":
                role = "model"
            else:
                role = "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})
        return contents

    def ask_sdk(self, client, messages):
        """Call Gemini one time and return the text of the reply."""
        system_text, others = self.split_system(messages)

        # [REQ: list/dict] Extra settings of the request are given as a dict.
        # We do not use the "function calling" feature, so turn it off
        # (the SDK prints a warning when it is left on).
        config = {"automatic_function_calling": {"disable": True}}
        if system_text != "":
            config["system_instruction"] = system_text

        response = client.models.generate_content(
            model=self.model,
            contents=self.convert_messages(others),
            config=config,
        )
        # response.text is None when the model returned no text.
        if response.text is None:
            return ""
        return response.text


# [REQ: class] ClaudeSdkProvider inherits from SdkProvider.
# It has its own attribute (max_tokens).
class ClaudeSdkProvider(SdkProvider):
    """Anthropic Claude, using the anthropic SDK."""

    SDK_NAME = "anthropic"

    def __init__(self, name, model, api_key="", timeout=60, max_retries=2):
        super().__init__(name, model, api_key, timeout, max_retries)
        # max_tokens: the longest reply allowed. The Claude API requires this value.
        self.max_tokens = 4096

    def create_client(self):
        """Import the Anthropic SDK and return its client."""
        import anthropic

        # max_retries=0: the SDK does not retry, because ChatProvider.chat() already does.
        return anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout, max_retries=0)

    def ask_sdk(self, client, messages):
        """Call Claude one time and return the text of the reply."""
        system_text, others = self.split_system(messages)

        # [REQ: if-else] Only send "system" when there is a system text.
        if system_text != "":
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_text,
                messages=others,
            )
        else:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=others,
            )

        # [REQ: for] The reply is a list of blocks. Keep the text blocks only
        # (a thinking model also returns "thinking" blocks).
        text = ""
        for block in response.content:
            if block.type == "text":
                text = text + block.text
        return text


# [REQ: class] OpenAISdkProvider inherits from SdkProvider.
class OpenAISdkProvider(SdkProvider):
    """OpenAI, using the openai SDK."""

    SDK_NAME = "openai"

    def create_client(self):
        """Import the OpenAI SDK and return its client."""
        import openai

        # max_retries=0: the SDK does not retry, because ChatProvider.chat() already does.
        return openai.OpenAI(api_key=self.api_key, timeout=self.timeout, max_retries=0)

    def ask_sdk(self, client, messages):
        """Call OpenAI one time and return the text of the reply."""
        # The messages are already in the OpenAI format, so no change is needed.
        response = client.chat.completions.create(model=self.model, messages=messages)

        content = response.choices[0].message.content
        # content is None when the model returned no text.
        if content is None:
            return ""
        return content


# ---------------------------------------------------------------------------
# The list of providers, and the functions that the GUI uses to pick one
# ---------------------------------------------------------------------------

# [REQ: list/dict] The two ways to call an LLM, shown in the first drop-down menu.
METHOD_LIST = ["HTTP", "SDK"]

# [REQ: list/dict] One dict per provider.
#   method         "HTTP" or "SDK"
#   type           used by create_provider() to choose the class
#   name           shown in the second drop-down menu
#   default_url    filled in the Base URL field when ".env" has no value
#   default_model  filled in the Model field when ".env" has no value
#   url_env, model_env, key_env
#                  names used in ".env" when the user presses "Save settings"
PROVIDER_LIST = [
    {
        "method": "HTTP", "type": "custom", "name": "Custom URL",
        "default_url": HttpProvider.DEFAULT_URL, "default_model": "",
        "url_env": "CUSTOM_BASE_URL", "model_env": "CUSTOM_MODEL", "key_env": "CUSTOM_API_KEY",
    },
    {
        "method": "HTTP", "type": "lmstudio", "name": "LM Studio",
        "default_url": LMStudioProvider.DEFAULT_URL, "default_model": "",
        "url_env": "LMSTUDIO_BASE_URL", "model_env": "LMSTUDIO_MODEL", "key_env": "LMSTUDIO_API_KEY",
    },
    {
        "method": "HTTP", "type": "ollama", "name": "Ollama",
        "default_url": OllamaProvider.DEFAULT_URL, "default_model": "",
        "url_env": "OLLAMA_BASE_URL", "model_env": "OLLAMA_MODEL", "key_env": "OLLAMA_API_KEY",
    },
    {
        "method": "SDK", "type": "google", "name": "Google",
        "default_url": "", "default_model": "gemini-2.5-flash",
        "url_env": "", "model_env": "GEMINI_MODEL", "key_env": "GEMINI_API_KEY",
    },
    {
        "method": "SDK", "type": "claude", "name": "Claude",
        "default_url": "", "default_model": "claude-opus-5-5",
        "url_env": "", "model_env": "CLAUDE_MODEL", "key_env": "ANTHROPIC_API_KEY",
    },
    {
        "method": "SDK", "type": "openai", "name": "OpenAI",
        "default_url": "", "default_model": "gpt-4o-mini",
        "url_env": "", "model_env": "OPENAI_MODEL", "key_env": "OPENAI_API_KEY",
    },
]


def get_provider_names(method):
    """Return the names of the providers of one method ("HTTP" or "SDK") as a list."""
    names = []
    # [REQ: for] [REQ: if-else] Keep the providers that belong to this method.
    for info in PROVIDER_LIST:
        if info["method"] == method:
            names.append(info["name"])
    return names


def find_provider_info(name):
    """Return the dict in PROVIDER_LIST that has this name."""
    # [REQ: for]
    for info in PROVIDER_LIST:
        if info["name"] == name:
            return info
    raise InvalidSettingError("Provider", "Unknown provider: " + name)


def create_provider(info, base_url, model, api_key, timeout=60, max_retries=2):
    """Build one provider object from a dict of PROVIDER_LIST and the values typed in the GUI."""
    name = info["name"]
    kind = info["type"]

    # [REQ: if-else] Choose the class by the type. The HTTP classes also need the Base URL.
    if kind == "custom":
        return HttpProvider(name, base_url, model, api_key, timeout, max_retries)
    elif kind == "lmstudio":
        return LMStudioProvider(name, base_url, model, api_key, timeout, max_retries)
    elif kind == "ollama":
        return OllamaProvider(name, base_url, model, api_key, timeout, max_retries)
    elif kind == "google":
        return GoogleSdkProvider(name, model, api_key, timeout, max_retries)
    elif kind == "claude":
        return ClaudeSdkProvider(name, model, api_key, timeout, max_retries)
    elif kind == "openai":
        return OpenAISdkProvider(name, model, api_key, timeout, max_retries)
    else:
        raise InvalidSettingError("Provider", "Unknown provider type: " + kind)
