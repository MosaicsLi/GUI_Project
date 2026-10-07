# config.py - Read and save the settings in the ".env" file
#
# The user types the URL, the model and the API key in the GUI.
# ".env" only remembers these values for the next start.
#
# Assignment requirements covered in this file:
#   [REQ: file I/O]    load_env() reads ".env", save_env() writes ".env"
#   [REQ: for]         load_env() reads the file line by line, save_env() writes line by line
#   [REQ: if-else]     load_env() skips comments and empty lines
#   [REQ: list/dict]   the settings are kept in a dict, the lines of the file in a list
#   [REQ: exception]   load_env() handles a missing file, both functions raise ConfigError
#   [REQ: module]      re

import re

from errors import ConfigError

# One setting looks like NAME=value. The name uses letters, digits and "_".
SETTING_PATTERN = r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"


def load_env(path):
    """Read the ".env" file and return the settings as a dict.

    Returns an empty dict when the file does not exist, because the program
    can start without ".env" (the user types the settings in the GUI).
    """
    # [REQ: list/dict] settings maps the name of a setting to its value,
    # for example {"LMSTUDIO_MODEL": "my-model"}.
    settings = {}

    # [REQ: file I/O] [REQ: exception] Open the file and read all lines into a list.
    try:
        with open(path, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except FileNotFoundError:
        # No ".env" yet: this is normal on the first start.
        return settings
    except (OSError, ValueError) as error:
        # OSError: no permission, etc.  ValueError: the file is not UTF-8 text.
        raise ConfigError("Cannot read the settings file: " + str(error))

    # [REQ: for] Check the lines one by one.
    for line in lines:
        line = line.strip()

        # [REQ: if-else] Skip empty lines and comments, read the other lines.
        if line == "" or line.startswith("#"):
            continue

        # [REQ: module] re splits the line into the name and the value.
        match = re.match(SETTING_PATTERN, line)
        if match is None:
            # Not in the NAME=value format, so ignore this line.
            continue

        name = match.group(1)
        value = match.group(2).strip()

        # Remove the quotes of a value written as "value" or 'value'.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        settings[name] = value

    return settings


def save_env(path, settings):
    """Write the settings dict to the ".env" file.

    The whole file is written again, so comments typed by hand in ".env" are lost.
    """
    # [REQ: list/dict] Build the lines of the file in a list first.
    lines = ["# Settings saved by the GUI. Never commit this file."]

    # [REQ: for] One line per setting, sorted by name so the file is easy to read.
    for name in sorted(settings):
        lines.append(name + "=" + str(settings[name]))

    # [REQ: file I/O] [REQ: exception] Write the lines to the file.
    try:
        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    except OSError as error:
        raise ConfigError("Cannot save the settings file: " + str(error))
