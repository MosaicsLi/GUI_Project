# config.py - Read the settings from the ".env" file
#
# PLACEHOLDER: this file is not implemented yet.
#
# Assignment requirements planned for this file:
#   [REQ: file I/O]    load_env() reads the ".env" file
#   [REQ: for]         load_env() reads the file line by line
#   [REQ: if-else]     load_env() skips comments and empty lines
#   [REQ: exception]   load_env() handles a missing file
#   [REQ: module]      os, re
#
# Planned functions:
#   load_env(path)              - read ".env" and put each setting into os.environ
#   get_setting(name, default)  - return one setting, or the default value
