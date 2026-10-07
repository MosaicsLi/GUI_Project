# main.py - Entry point of the program
#
# How to run:
#   C:\Users\tamak\Documents\VSC\KIC\python\.venv\Scripts\python.exe main.py

from app import App


def main():
    """Build the window and start the GUI."""
    app = App()
    app.run()


# This part only runs when the file is started directly, not when it is imported.
if __name__ == "__main__":
    main()
