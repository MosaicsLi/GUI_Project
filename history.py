# history.py - Save the chat records, export them, and calculate statistics
#
# The records never contain the API key or the Base URL.
#
# Assignment requirements covered in this file:
#   [REQ: file I/O]    HistoryStore.load(), save(), export_csv(), backup_broken_file()
#   [REQ: for]         load(), save(), export_csv(), stats_by_provider()
#   [REQ: while]       backup_broken_file()
#   [REQ: if-else]     stats_by_provider()
#   [REQ: list/dict]   HistoryStore.records, ChatRecord.to_dict(), the result of stats_by_provider()
#   [REQ: class]       ChatRecord, HistoryStore
#   [REQ: exception]   load() handles a missing or broken file, save() and export_csv() raise StorageError
#   [REQ: module]      json, csv, datetime, statistics, os

import csv
import datetime
import json
import os
import statistics

from errors import StorageError

# Names of the columns of the CSV file, in the order they are written.
CSV_COLUMNS = ["timestamp", "method", "provider", "model", "seconds", "prompt", "reply"]


# [REQ: class] One record of the history.
class ChatRecord:
    """One question, its reply, and how long the provider took to answer."""

    def __init__(self, method, provider, model, prompt, reply, seconds, timestamp=None):
        # method: "HTTP" or "SDK"
        self.method = method
        # provider: name of the provider, for example "LM Studio"
        self.provider = provider
        # model: name of the model that answered
        self.model = model
        # prompt: the text the user sent
        self.prompt = prompt
        # reply: the text the model returned
        self.reply = reply
        # seconds: how long the reply took
        self.seconds = seconds
        # timestamp: when the record was made, as text like "2026-10-07 14:30:05"
        # [REQ: if-else] [REQ: module] A new record gets the current time from datetime.
        if timestamp is None:
            self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            self.timestamp = timestamp

    def to_dict(self):
        """Return the record as a dict, so it can be saved as JSON."""
        # [REQ: list/dict]
        return {
            "timestamp": self.timestamp,
            "method": self.method,
            "provider": self.provider,
            "model": self.model,
            "seconds": self.seconds,
            "prompt": self.prompt,
            "reply": self.reply,
        }


def record_from_dict(data):
    """Build a ChatRecord from a dict that was read from the JSON file."""
    return ChatRecord(
        data["method"],
        data["provider"],
        data["model"],
        data["prompt"],
        data["reply"],
        float(data["seconds"]),
        data["timestamp"],
    )


# [REQ: class] All the records, and the file they are saved in.
class HistoryStore:
    """Keep the list of ChatRecord and save it in a JSON file."""

    def __init__(self, path):
        # path: the JSON file, for example "data/history.json"
        self.path = path
        # [REQ: list/dict] records: list of ChatRecord, oldest first
        self.records = []

    def load(self):
        """Read the records from the JSON file. A missing file means no records yet."""
        # [REQ: file I/O] [REQ: exception] [REQ: module] json.load turns the file into a list of dict.
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                items = json.load(file)
        except FileNotFoundError:
            # First start: there is no history yet.
            self.records = []
            return
        except (OSError, ValueError) as error:
            # OSError: cannot open the file.  ValueError: the file is not valid JSON.
            raise StorageError("Cannot read the history file: " + str(error))

        # [REQ: for] [REQ: exception] Turn each dict back into a ChatRecord.
        records = []
        try:
            for item in items:
                records.append(record_from_dict(item))
        except (KeyError, TypeError, ValueError):
            raise StorageError("The history file has an unexpected format: " + self.path)
        self.records = records

    def backup_broken_file(self):
        """Rename a broken history file to ".bak" and return the new path.

        The broken file is kept, so the user can still open it and rescue the text.
        After this the program can start again with an empty history.
        """
        backup_path = self.path + ".bak"
        number = 2
        # [REQ: while] Never overwrite an older backup: try ".bak", ".bak2", ".bak3", ...
        # until a name is free.
        while os.path.exists(backup_path):
            backup_path = self.path + ".bak" + str(number)
            number = number + 1

        # [REQ: file I/O] [REQ: exception] os.rename gives the file its new name.
        try:
            os.rename(self.path, backup_path)
        except OSError as error:
            raise StorageError("Cannot rename the broken history file: " + str(error))

        self.records = []
        return backup_path

    def save(self):
        """Write all the records to the JSON file."""
        # [REQ: for] [REQ: list/dict] JSON cannot save objects, so make a list of dict first.
        items = []
        for record in self.records:
            items.append(record.to_dict())

        # [REQ: file I/O] [REQ: exception] Create the folder when needed, then write the file.
        try:
            folder = os.path.dirname(self.path)
            if folder != "":
                os.makedirs(folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as file:
                # ensure_ascii=False keeps Chinese and Japanese text readable in the file.
                json.dump(items, file, ensure_ascii=False, indent=2)
        except OSError as error:
            raise StorageError("Cannot save the history file: " + str(error))

    def add(self, record):
        """Add one record and save the file at once, so nothing is lost if the program closes."""
        self.records.append(record)
        self.save()

    def export_csv(self, path):
        """Write all the records to a CSV file and return how many records were written."""
        # [REQ: file I/O] [REQ: exception] [REQ: module] csv.writer takes care of commas,
        # quotes and new lines inside the text.
        try:
            folder = os.path.dirname(path)
            if folder != "":
                os.makedirs(folder, exist_ok=True)
            # newline="" is required by the csv module.
            # utf-8-sig lets Excel show Chinese and Japanese text correctly.
            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(CSV_COLUMNS)
                # [REQ: for] One row per record, the columns in the order of CSV_COLUMNS.
                for record in self.records:
                    data = record.to_dict()
                    row = []
                    for column in CSV_COLUMNS:
                        row.append(data[column])
                    writer.writerow(row)
        except OSError as error:
            raise StorageError("Cannot save the CSV file: " + str(error))
        return len(self.records)

    def stats_by_provider(self):
        """Return the statistics of the reply time of each provider.

        Example of the result:
            {"LM Studio": {"count": 3, "mean": 2.41, "median": 2.3}}
        """
        # [REQ: list/dict] [REQ: for] [REQ: if-else] Group the seconds by provider:
        # {"LM Studio": [2.4, 2.1, 2.7], "Claude": [1.5]}
        groups = {}
        for record in self.records:
            if record.provider not in groups:
                groups[record.provider] = []
            groups[record.provider].append(record.seconds)

        # [REQ: for] [REQ: module] statistics calculates the mean and the median of each list.
        stats = {}
        for provider in groups:
            seconds_list = groups[provider]
            stats[provider] = {
                "count": len(seconds_list),
                "mean": round(statistics.mean(seconds_list), 2),
                "median": round(statistics.median(seconds_list), 2),
            }
        return stats
