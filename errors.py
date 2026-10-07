# errors.py - Custom exceptions used by the whole program
#
# Assignment requirements covered in this file:
#   [REQ: class]      LLMError is the parent class, the other six classes inherit from it
#   [REQ: exception]  These classes are raised and caught in providers.py and app.py


# [REQ: class] [REQ: exception] Parent class of every custom exception.
# Catching LLMError also catches all of the subclasses below.
class LLMError(Exception):
    """Parent class of all errors raised by this program."""

    def __init__(self, message):
        super().__init__(message)
        # message: text that the GUI shows to the user
        self.message = message

    def get_title(self):
        """Return the title of the error dialog."""
        return "LLM Error"


# [REQ: class] Subclass of LLMError with its own attribute and its own method.
class MissingKeyError(LLMError):
    """The provider needs an API key but the API Key field is empty."""

    def __init__(self, provider_name):
        super().__init__(provider_name + " needs an API key. Please type it in the API Key field.")
        # provider_name: name of the provider that needs the key
        self.provider_name = provider_name

    def get_title(self):
        """Return the title of the error dialog."""
        return "Missing API Key"


# [REQ: class] Subclass of LLMError with its own attribute and its own method.
class InvalidSettingError(LLMError):
    """A field typed in the GUI is empty or wrong (for example the Base URL)."""

    def __init__(self, field_name, reason):
        super().__init__(field_name + ": " + reason)
        # field_name: name of the field that the user has to fix
        self.field_name = field_name

    def get_title(self):
        """Return the title of the error dialog."""
        return "Invalid Setting"


# [REQ: class] Subclass of LLMError with its own attribute and its own method.
class ConnectionFailedError(LLMError):
    """Cannot connect, timeout, HTTP error, or an API error reported by an SDK."""

    def __init__(self, message, can_retry=True):
        super().__init__(message)
        # can_retry: True when trying again may work (server busy, timeout).
        # False when trying again is useless (wrong key, wrong model name).
        self.can_retry = can_retry

    def get_title(self):
        """Return the title of the error dialog."""
        return "Connection Failed"


# [REQ: class] Subclass of LLMError.
class BadResponseError(LLMError):
    """The reply is empty or is not in the expected format."""

    def get_title(self):
        """Return the title of the error dialog."""
        return "Bad Response"


# [REQ: class] Subclass of LLMError with its own attribute and its own method.
class SdkMissingError(LLMError):
    """The SDK package of the provider is not installed."""

    def __init__(self, sdk_name):
        super().__init__("SDK is not installed. Please run: pip install " + sdk_name)
        # sdk_name: name of the package to install with pip
        self.sdk_name = sdk_name

    def get_title(self):
        """Return the title of the error dialog."""
        return "SDK Not Installed"


# [REQ: class] Subclass of LLMError.
class ConfigError(LLMError):
    """The ".env" file cannot be read or cannot be saved."""

    def get_title(self):
        """Return the title of the error dialog."""
        return "Config Error"
