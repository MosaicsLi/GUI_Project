# app.py - The GUI window (tkinter)
#
# PLACEHOLDER: this file is not implemented yet.
#
# Assignment requirements planned for this file:
#   [REQ: if-else]     on_method_changed(), check_result()
#   [REQ: while]       trim_messages(), check_result()
#   [REQ: for]         show_stats()
#   [REQ: range]       show_stats()
#   [REQ: list/dict]   messages, settings, SAMPLE_PROMPTS, items in result_queue
#   [REQ: class]       App
#   [REQ: file I/O]    on_save_settings(), on_export()
#   [REQ: exception]   call_in_thread(), check_result()
#   [REQ: module]      tkinter, threading, queue, random, datetime, time
#
# Planned class:
#   App
#     - two drop-down menus: call method (HTTP / SDK) and provider
#     - settings fields typed by the user: Base URL, Model, API Key
#     - "Save settings" button that writes the fields to ".env"
#     - chat area, input box, Send button, Cancel button
#
# Thread rules (the API is called in a background thread):
#   1. Widgets are only used in the main thread.
#   2. The background thread gives its result back through a queue.
#   3. The background thread gets a copy of the messages list.
