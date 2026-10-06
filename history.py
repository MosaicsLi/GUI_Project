# history.py - Save the chat records, export them, and calculate statistics
#
# PLACEHOLDER: this file is not implemented yet.
#
# Assignment requirements planned for this file:
#   [REQ: file I/O]    HistoryStore.load(), save(), export_csv()
#   [REQ: for]         HistoryStore.export_csv(), stats_by_provider()
#   [REQ: list/dict]   HistoryStore.records, ChatRecord.to_dict()
#   [REQ: class]       ChatRecord, HistoryStore
#   [REQ: exception]   HistoryStore.load() handles a missing or broken file
#   [REQ: module]      json, csv, datetime, statistics
#
# Planned classes:
#   ChatRecord    - one question and its reply
#   HistoryStore  - list of ChatRecord, saved in data/history.json
