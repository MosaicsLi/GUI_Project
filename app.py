# app.py - The GUI window (tkinter)
#
# Assignment requirements covered in this file:
#   [REQ: if-else]     fill_fields(), on_send(), handle_result(), set_busy()
#   [REQ: while]       trim_messages(), check_result()
#   [REQ: for]         show_stats()
#   [REQ: range]       show_stats()
#   [REQ: list/dict]   messages, settings, SAMPLE_PROMPTS, the result dict put in result_queue
#   [REQ: class]       App
#   [REQ: file I/O]    on_save_settings() writes ".env", save_record() writes the history,
#                      on_export() writes the CSV file (through config.py and history.py)
#   [REQ: exception]   call_in_thread(), check_result(), load_history(), on_send(), on_export()
#   [REQ: module]      tkinter, threading, queue, random, time, os
#
# Thread rules (the API is called in a background thread, so the window never freezes):
#   1. Widgets are only used in the main thread.
#   2. The background thread gives its result back through a queue.
#   3. The background thread gets a copy of the messages list.

import os
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from config import load_env, save_env
from errors import LLMError, StorageError
from history import ChatRecord, HistoryStore
from providers import METHOD_LIST, PROVIDER_LIST
from providers import create_provider, find_provider_info, get_provider_names

# The files are next to this program, so it works from any current folder.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
HISTORY_PATH = os.path.join(BASE_DIR, "data", "history.json")

# How often the main thread looks into the queue, in milliseconds.
POLL_MS = 100

# The longest conversation that is sent to the model. Older messages are dropped.
MAX_MESSAGES = 20

# [REQ: list/dict] Prompts for the "Sample prompt" button, handy to compare the providers.
SAMPLE_PROMPTS = [
    "Explain what an API is in two sentences.",
    "Write a haiku about autumn.",
    "What is the difference between a list and a dict in Python?",
    "Give me three ideas for a weekend trip.",
    "Translate 'Good morning, how are you?' into Japanese.",
    "Explain recursion to a ten-year-old child.",
]


# [REQ: class] The window of the program.
class App:
    """The main window: choose a provider, type the settings, and chat."""

    def __init__(self, env_path=ENV_PATH, history_path=HISTORY_PATH):
        self.root = tk.Tk()
        self.root.title("GUI_LLMConsento")
        self.root.geometry("780x680")
        self.root.minsize(560, 480)

        # env_path: where "Save settings" writes
        self.env_path = env_path

        # [REQ: list/dict] settings: everything read from ".env", name -> value.
        # It also remembers what the user typed for each provider while the program runs.
        try:
            self.settings = load_env(self.env_path)
        except LLMError as error:
            self.settings = {}
            self.show_error(error)

        # current_info: the dict of PROVIDER_LIST that is selected now
        self.current_info = None

        # [REQ: list/dict] messages: the conversation, a list of dict in the OpenAI format
        self.messages = []

        self.history = HistoryStore(history_path)
        self.load_history()

        # ----- thread -----
        # result_queue: the background thread puts its result here
        self.result_queue = queue.Queue()
        # worker: the background thread that is calling the API
        self.worker = None
        # request_id: number of the newest request. A result with an older number is ignored.
        self.request_id = 0
        # is_busy: True while we wait for a reply
        self.is_busy = False
        # busy_kind: what we are waiting for, "chat" or "models"
        self.busy_kind = ""
        # [REQ: list/dict] pending: facts about the question that is waiting for its reply,
        # kept for the history record
        self.pending = {}
        # after_id: id of the next check_result() call, needed to cancel it when closing
        self.after_id = None

        self.build_widgets()
        self.select_first_provider()

        # Run on_close() when the user presses the X button of the window.
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def load_history(self):
        """Read the old records. A broken file is renamed to ".bak" and kept."""
        # [REQ: exception] A broken history file must not stop the program from starting.
        try:
            self.history.load()
        except StorageError as error:
            try:
                backup_path = self.history.backup_broken_file()
                messagebox.showwarning(
                    "History File",
                    error.message + "\n\nThe broken file was kept as:\n" + backup_path
                    + "\n\nThe program starts with an empty history.",
                )
            except StorageError as rename_error:
                self.show_error(rename_error)

    def build_widgets(self):
        """Create every widget of the window."""
        # ----- settings area -----
        settings_frame = ttk.LabelFrame(self.root, text="Settings", padding=8)
        settings_frame.pack(fill="x", padx=10, pady=(10, 5))
        # Column 1 holds the input fields and takes all the extra width.
        settings_frame.columnconfigure(1, weight=1)

        # Row 0: the two drop-down menus.
        ttk.Label(settings_frame, text="Call method").grid(row=0, column=0, sticky="w", pady=2)
        menu_frame = ttk.Frame(settings_frame)
        menu_frame.grid(row=0, column=1, columnspan=2, sticky="w", pady=2)

        # state="readonly": the user can only choose from the list.
        self.method_box = ttk.Combobox(menu_frame, values=METHOD_LIST, state="readonly", width=10)
        self.method_box.pack(side="left")
        self.method_box.bind("<<ComboboxSelected>>", self.on_method_changed)

        ttk.Label(menu_frame, text="Provider").pack(side="left", padx=(15, 5))
        self.provider_box = ttk.Combobox(menu_frame, state="readonly", width=18)
        self.provider_box.pack(side="left")
        self.provider_box.bind("<<ComboboxSelected>>", self.on_provider_changed)

        # Row 1: Base URL (only shown for the HTTP method).
        # A StringVar holds the text of a field, so we can read and change it.
        self.url_var = tk.StringVar()
        self.url_label = ttk.Label(settings_frame, text="Base URL")
        self.url_label.grid(row=1, column=0, sticky="w", pady=2)
        self.url_entry = ttk.Entry(settings_frame, textvariable=self.url_var)
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=2)

        # Row 2: Model. The user can type a name, or press "Load models" (HTTP method only)
        # and choose from the list that the server returns.
        self.model_var = tk.StringVar()
        ttk.Label(settings_frame, text="Model").grid(row=2, column=0, sticky="w", pady=2)
        self.model_box = ttk.Combobox(settings_frame, textvariable=self.model_var)
        self.model_box.grid(row=2, column=1, sticky="ew", pady=2)
        self.load_button = ttk.Button(settings_frame, text="Load models", command=self.on_load_models)
        self.load_button.grid(row=2, column=2, padx=(8, 0), pady=2)

        # Row 3: API key, hidden with "*" until the user ticks "Show".
        self.key_var = tk.StringVar()
        ttk.Label(settings_frame, text="API Key").grid(row=3, column=0, sticky="w", pady=2, padx=(0, 10))
        self.key_entry = ttk.Entry(settings_frame, textvariable=self.key_var, show="*")
        self.key_entry.grid(row=3, column=1, sticky="ew", pady=2)
        self.show_key_var = tk.BooleanVar(value=False)
        self.show_key_check = ttk.Checkbutton(
            settings_frame, text="Show", variable=self.show_key_var, command=self.on_toggle_key
        )
        self.show_key_check.grid(row=3, column=2, padx=(8, 0))

        # Row 4: save button.
        self.save_button = ttk.Button(settings_frame, text="Save settings", command=self.on_save_settings)
        self.save_button.grid(row=4, column=1, sticky="w", pady=(6, 0))

        # ----- tool buttons -----
        tool_frame = ttk.Frame(self.root)
        tool_frame.pack(fill="x", padx=10)
        self.sample_button = ttk.Button(tool_frame, text="Sample prompt", command=self.on_sample_prompt)
        self.sample_button.pack(side="left")
        self.clear_button = ttk.Button(tool_frame, text="Clear chat", command=self.on_clear)
        self.clear_button.pack(side="left", padx=(6, 0))
        self.stats_button = ttk.Button(tool_frame, text="Statistics", command=self.show_stats)
        self.stats_button.pack(side="right")
        self.export_button = ttk.Button(tool_frame, text="Export CSV", command=self.on_export)
        self.export_button.pack(side="right", padx=(0, 6))

        # ----- bottom area (packed before the chat area, so it keeps its height) -----
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        self.status_label.pack(side="bottom", fill="x", padx=10, pady=(0, 6))

        input_frame = ttk.Frame(self.root)
        input_frame.pack(side="bottom", fill="x", padx=10, pady=5)

        button_frame = ttk.Frame(input_frame)
        button_frame.pack(side="right", fill="y", padx=(8, 0))
        self.send_button = ttk.Button(button_frame, text="Send", command=self.on_send)
        self.send_button.pack(fill="x")
        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.on_cancel, state="disabled")
        self.cancel_button.pack(fill="x", pady=(4, 0))

        self.input_box = tk.Text(input_frame, height=4, wrap="word", font=("Segoe UI", 10))
        self.input_box.pack(side="left", fill="both", expand=True)
        # Ctrl+Enter sends the message, Enter alone makes a new line.
        self.input_box.bind("<Control-Return>", self.on_send_key)

        # ----- chat area (takes all the space that is left) -----
        self.chat_box = ScrolledText(self.root, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.chat_box.pack(fill="both", expand=True, padx=10, pady=5)
        # A tag is a named style for a part of the text.
        self.chat_box.tag_configure("speaker", font=("Segoe UI", 10, "bold"))
        self.chat_box.tag_configure("note", foreground="gray40")

        self.input_box.focus_set()

    def select_first_provider(self):
        """Choose the provider shown at the start: the one saved last time, or the first one."""
        # [REQ: exception] The saved name may be unknown (an old or hand-edited ".env").
        try:
            info = find_provider_info(self.settings.get("LAST_PROVIDER", ""))
        except LLMError:
            info = PROVIDER_LIST[0]

        self.method_box.set(info["method"])
        self.provider_box["values"] = get_provider_names(info["method"])
        self.provider_box.set(info["name"])
        self.on_provider_changed()

    # ------------------------------------------------------------------
    # Settings fields
    # ------------------------------------------------------------------

    def on_method_changed(self, event=None):
        """The first drop-down menu changed: fill the second one with the providers of this method."""
        names = get_provider_names(self.method_box.get())
        self.provider_box["values"] = names
        self.provider_box.set(names[0])
        self.on_provider_changed()

    def on_provider_changed(self, event=None):
        """The second drop-down menu changed: show the settings of the new provider."""
        # Remember what the user typed for the old provider before the fields change.
        if self.current_info is not None:
            self.store_fields()

        self.current_info = find_provider_info(self.provider_box.get())
        self.fill_fields()

    def get_saved(self, env_name, default):
        """Return one value of settings, or the default when it is missing or empty."""
        value = self.settings.get(env_name, "")
        if value == "":
            return default
        return value

    def fill_fields(self):
        """Put the settings of the current provider into the fields."""
        info = self.current_info

        # [REQ: if-else] Only the HTTP method has a Base URL, so hide the row for the SDK method.
        # "Load models" asks the server at the Base URL, so it is hidden too.
        if info["method"] == "HTTP":
            self.url_label.grid()
            self.url_entry.grid()
            self.load_button.grid()
            self.url_var.set(self.get_saved(info["url_env"], info["default_url"]))
        else:
            self.url_label.grid_remove()
            self.url_entry.grid_remove()
            self.load_button.grid_remove()
            self.url_var.set("")

        self.model_var.set(self.get_saved(info["model_env"], info["default_model"]))
        self.key_var.set(self.get_saved(info["key_env"], ""))
        # The model list belongs to the old provider, so empty it.
        self.model_box["values"] = []

    def read_fields(self):
        """Return what the user typed in the three fields as a dict, without spaces around."""
        # [REQ: list/dict]
        return {
            "base_url": self.url_var.get().strip(),
            "model": self.model_var.get().strip(),
            "api_key": self.key_var.get().strip(),
        }

    def store_fields(self):
        """Copy the fields into settings, under the ".env" names of the current provider."""
        info = self.current_info
        fields = self.read_fields()

        # [REQ: if-else] An SDK provider has no Base URL to remember.
        if info["url_env"] != "":
            self.settings[info["url_env"]] = fields["base_url"]
        self.settings[info["model_env"]] = fields["model"]
        self.settings[info["key_env"]] = fields["api_key"]
        self.settings["LAST_PROVIDER"] = info["name"]

    def get_number(self, env_name, default):
        """Return one value of settings as a whole number, or the default when it is not a number."""
        # [REQ: exception] The user may have typed something else than a number in ".env".
        try:
            return int(self.settings.get(env_name, default))
        except ValueError:
            return default

    def on_toggle_key(self):
        """Show the API key as text, or hide it with "*"."""
        if self.show_key_var.get():
            self.key_entry.config(show="")
        else:
            self.key_entry.config(show="*")

    def on_save_settings(self):
        """Write the settings of every provider to ".env", so the next start remembers them."""
        self.store_fields()
        # [REQ: file I/O] [REQ: exception] save_env() writes the file and may raise ConfigError.
        try:
            save_env(self.env_path, self.settings)
            self.status_var.set("Settings saved to " + self.env_path)
        except LLMError as error:
            self.show_error(error)

    # ------------------------------------------------------------------
    # Sending a message (main thread)
    # ------------------------------------------------------------------

    def on_send_key(self, event):
        """Ctrl+Enter was pressed in the input box."""
        self.on_send()
        # "break" stops tkinter from also adding a new line to the input box.
        return "break"

    def on_send(self):
        """Send the text of the input box to the current provider."""
        # [REQ: if-else] Only one request at a time.
        if self.is_busy:
            return

        prompt = self.input_box.get("1.0", "end").strip()
        if prompt == "":
            self.status_var.set("Please type a message first.")
            return

        # Thread rule 1: read the widgets here, in the main thread.
        info = self.current_info
        fields = self.read_fields()

        # [REQ: exception] Check the settings before starting the thread,
        # so a missing key or a bad URL is reported at once.
        try:
            provider = create_provider(
                info,
                fields["base_url"],
                fields["model"],
                fields["api_key"],
                self.get_number("LLM_TIMEOUT", 60),
                self.get_number("LLM_MAX_RETRIES", 2),
            )
            provider.check_settings()
        except LLMError as error:
            self.show_error(error)
            return

        # [REQ: list/dict] Add the question to the conversation and show it.
        self.messages.append({"role": "user", "content": prompt})
        self.trim_messages()
        self.append_chat("You", prompt)
        self.input_box.delete("1.0", "end")
        self.pending = {"method": info["method"], "prompt": prompt}

        # A new number for this request. See on_cancel() and handle_result().
        self.request_id = self.request_id + 1
        self.set_busy(True, "chat")

        # Thread rule 3: list(...) makes a copy, so the thread has its own list.
        # daemon=True: the thread does not keep the program alive after the window is closed.
        self.worker = threading.Thread(
            target=self.call_in_thread,
            args=(provider, list(self.messages), self.request_id),
            daemon=True,
        )
        self.worker.start()

        # Start looking into the queue.
        self.after_id = self.root.after(POLL_MS, self.check_result)

    def trim_messages(self):
        """Drop the oldest messages when the conversation is longer than MAX_MESSAGES.

        Every message is sent again with each question, so a very long conversation
        gets slow, costs more, and may not fit in the model.
        """
        # [REQ: while] Remove one question and its answer at a time, so the
        # conversation still starts with a question (Claude and Gemini require that).
        while len(self.messages) > MAX_MESSAGES:
            self.messages.pop(0)
            self.messages.pop(0)

    def on_load_models(self):
        """Ask the server for its models and put them in the Model drop-down menu (HTTP method only)."""
        if self.is_busy:
            return

        # Thread rule 1: read the widgets here, in the main thread.
        info = self.current_info
        fields = self.read_fields()

        # [REQ: exception] Check the Base URL before starting the thread.
        try:
            provider = create_provider(
                info,
                fields["base_url"],
                fields["model"],
                fields["api_key"],
                self.get_number("LLM_TIMEOUT", 60),
                self.get_number("LLM_MAX_RETRIES", 2),
            )
            provider.check_url()
        except LLMError as error:
            self.show_error(error)
            return

        self.request_id = self.request_id + 1
        self.set_busy(True, "models")
        self.worker = threading.Thread(
            target=self.load_models_in_thread,
            args=(provider, self.request_id),
            daemon=True,
        )
        self.worker.start()
        self.after_id = self.root.after(POLL_MS, self.check_result)

    def on_cancel(self):
        """Stop waiting for the reply.

        A network request cannot be stopped halfway. The thread finishes on its own
        in the background, and its result is ignored because request_id has changed.
        """
        if not self.is_busy:
            return

        # From now on the running request has an old number.
        self.request_id = self.request_id + 1
        # [REQ: if-else] The question got no answer, so take it out of the conversation again.
        if self.busy_kind == "chat":
            self.messages.pop()
            self.append_note("Cancelled.")
        self.set_busy(False)
        self.status_var.set("Cancelled")

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def call_in_thread(self, provider, messages, request_id):
        """Call the API. This method runs in the background thread.

        Thread rule 1: it must not touch any widget.
        Thread rule 2: it gives its result back through result_queue.
        """
        start_time = time.time()

        # [REQ: exception] [REQ: list/dict] Whatever happens, put one result dict in the queue.
        # Without a result the window would wait forever.
        try:
            reply = provider.chat(messages)
            result = {"ok": True, "reply": reply}
        except LLMError as error:
            result = {"ok": False, "title": error.get_title(), "message": error.message}
        except Exception as error:
            # A bug or something we did not expect.
            result = {"ok": False, "title": "Unexpected Error", "message": str(error)}

        result["id"] = request_id
        result["kind"] = "chat"
        result["provider"] = provider.name
        result["model"] = provider.model
        result["seconds"] = round(time.time() - start_time, 2)
        self.result_queue.put(result)

    def load_models_in_thread(self, provider, request_id):
        """Ask the server for its list of models. This method runs in the background thread."""
        # [REQ: exception] [REQ: list/dict] Same rules as call_in_thread().
        try:
            names = provider.list_models()
            result = {"ok": True, "names": names}
        except LLMError as error:
            result = {"ok": False, "title": error.get_title(), "message": error.message}
        except Exception as error:
            result = {"ok": False, "title": "Unexpected Error", "message": str(error)}

        result["id"] = request_id
        result["kind"] = "models"
        self.result_queue.put(result)

    # ------------------------------------------------------------------
    # Receiving the result (main thread)
    # ------------------------------------------------------------------

    def check_result(self):
        """Look into the queue. The main thread calls this again and again while it waits."""
        # [REQ: while] [REQ: exception] Take out everything that is in the queue now.
        # get_nowait() raises queue.Empty when nothing is left.
        while True:
            try:
                result = self.result_queue.get_nowait()
            except queue.Empty:
                break
            self.handle_result(result)

        # [REQ: if-else] Still waiting: look again a little later.
        if self.is_busy:
            self.after_id = self.root.after(POLL_MS, self.check_result)
        else:
            self.after_id = None

    def handle_result(self, result):
        """Show one result that came from the background thread."""
        # [REQ: if-else] A result of a cancelled request has an old number: ignore it.
        if result["id"] != self.request_id:
            return

        # [REQ: if-else] The queue carries two kinds of results.
        if result["kind"] == "models":
            self.handle_models(result)
        else:
            self.handle_chat(result)

    def handle_chat(self, result):
        """Show the reply of the model, or the error."""
        if result["ok"]:
            self.messages.append({"role": "assistant", "content": result["reply"]})
            self.append_chat(result["provider"], result["reply"])
            self.set_busy(False)
            self.status_var.set("Reply from " + result["provider"] + " in " + str(result["seconds"]) + " s")
            self.save_record(result)
        else:
            # The question got no answer, so take it out of the conversation again.
            self.messages.pop()
            self.append_note("Error: " + result["message"])
            self.set_busy(False)
            self.status_var.set(result["title"])
            messagebox.showerror(result["title"], result["message"])

    def handle_models(self, result):
        """Put the list of models into the Model drop-down menu, or show the error."""
        self.set_busy(False)
        if result["ok"]:
            names = result["names"]
            self.model_box["values"] = names
            # Fill in the first model when the field is still empty.
            if self.model_var.get().strip() == "" and len(names) > 0:
                self.model_var.set(names[0])
            self.status_var.set(str(len(names)) + " models found. Choose one in the Model field.")
        else:
            self.status_var.set(result["title"])
            messagebox.showerror(result["title"], result["message"])

    def save_record(self, result):
        """Add one finished question and reply to the history file."""
        record = ChatRecord(
            self.pending["method"],
            result["provider"],
            result["model"],
            self.pending["prompt"],
            result["reply"],
            result["seconds"],
        )
        # [REQ: file I/O] [REQ: exception] add() writes the JSON file. A failed save
        # must not stop the chat, so only show a gray note.
        try:
            self.history.add(record)
        except StorageError as error:
            self.append_note("Warning: " + error.message)

    # ------------------------------------------------------------------
    # Tool buttons
    # ------------------------------------------------------------------

    def on_sample_prompt(self):
        """Put a random sample prompt into the input box."""
        # [REQ: module] random.choice picks one item of the list.
        prompt = random.choice(SAMPLE_PROMPTS)
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", prompt)
        self.input_box.focus_set()

    def on_clear(self):
        """Start a new conversation. The history file is not changed."""
        # [REQ: if-else] The waiting question is part of the conversation, so do not clear now.
        if self.is_busy:
            self.status_var.set("Please wait for the reply, or press Cancel first.")
            return

        self.messages = []
        self.chat_box.config(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.config(state="disabled")
        self.status_var.set("Chat cleared")

    def on_export(self):
        """Ask where to save, then write every record of the history to a CSV file."""
        if len(self.history.records) == 0:
            messagebox.showinfo("Export CSV", "There are no records yet. Send a message first.")
            return

        # The dialog opens in the folder of the history file.
        folder = os.path.dirname(self.history.path)
        path = filedialog.asksaveasfilename(
            title="Export CSV",
            initialdir=folder,
            initialfile="export.csv",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
        )
        # The dialog returns an empty text when the user presses Cancel.
        if path == "":
            return

        # [REQ: file I/O] [REQ: exception] export_csv() writes the file and may raise StorageError.
        try:
            count = self.history.export_csv(path)
            self.status_var.set(str(count) + " records exported to " + path)
        except StorageError as error:
            self.show_error(error)

    def show_stats(self):
        """Open a window with a bar chart of the average reply time of each provider."""
        # [REQ: list/dict] stats looks like {"LM Studio": {"count": 3, "mean": 2.41, "median": 2.3}}
        stats = self.history.stats_by_provider()
        if len(stats) == 0:
            messagebox.showinfo("Statistics", "There are no records yet. Send a message first.")
            return

        names = sorted(stats)

        # The longest bar belongs to the slowest provider.
        longest = 0
        for name in names:
            if stats[name]["mean"] > longest:
                longest = stats[name]["mean"]
        if longest == 0:
            longest = 1

        # Sizes of the chart in pixels.
        row_height = 46
        name_width = 110
        bar_max = 260
        top = 50

        window = tk.Toplevel(self.root)
        window.title("Statistics")
        window.resizable(False, False)
        canvas = tk.Canvas(window, width=680, height=top + row_height * len(names) + 20, bg="white")
        canvas.pack(padx=10, pady=10)
        canvas.create_text(15, 22, anchor="w", text="Average reply time (seconds)", font=("Segoe UI", 11, "bold"))

        # [REQ: for] [REQ: range] One row per provider. The number i gives the row
        # its place: row 0 is at the top, row 1 is one row_height lower, and so on.
        for i in range(len(names)):
            name = names[i]
            item = stats[name]
            y = top + row_height * i
            bar_length = bar_max * item["mean"] / longest

            canvas.create_text(15, y + 12, anchor="w", text=name, font=("Segoe UI", 10))
            canvas.create_rectangle(name_width, y, name_width + bar_length, y + 24, fill="steelblue", outline="")
            # [REQ: if-else] "1 reply" but "2 replies".
            if item["count"] == 1:
                count_text = "1 reply"
            else:
                count_text = str(item["count"]) + " replies"
            label = str(item["mean"]) + " s   (median " + str(item["median"]) + " s, " + count_text + ")"
            canvas.create_text(name_width + bar_length + 8, y + 12, anchor="w", text=label, font=("Segoe UI", 9))

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def set_busy(self, busy, kind=""):
        """Switch the buttons between "waiting" and "ready". kind is "chat" or "models"."""
        self.is_busy = busy
        self.busy_kind = kind
        # [REQ: if-else] Only one background job at a time, so Send and Load models
        # are both switched off while we wait.
        if busy:
            self.send_button.config(state="disabled")
            self.load_button.config(state="disabled")
            self.cancel_button.config(state="normal")
            if kind == "models":
                self.status_var.set("Loading the list of models...")
            else:
                self.status_var.set("Waiting for the reply...")
        else:
            self.send_button.config(state="normal")
            self.load_button.config(state="normal")
            self.cancel_button.config(state="disabled")
            self.status_var.set("Ready")

    def append_chat(self, speaker, text):
        """Add one message to the chat area."""
        # The chat area is read-only for the user, so unlock it while we write.
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", speaker + "\n", "speaker")
        self.chat_box.insert("end", text + "\n\n")
        self.chat_box.config(state="disabled")
        # Scroll down to the newest message.
        self.chat_box.see("end")

    def append_note(self, text):
        """Add a gray line to the chat area that is not part of the conversation."""
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", text + "\n\n", "note")
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    def show_error(self, error):
        """Show one of our own errors in a dialog."""
        messagebox.showerror(error.get_title(), error.message)

    def on_close(self):
        """Close the window."""
        # Stop the next check_result() call, so it does not run on a closed window.
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        # A thread that is still running is a daemon thread, so it ends with the program.
        self.root.destroy()

    def run(self):
        """Start the GUI. This call returns when the window is closed."""
        self.root.mainloop()
