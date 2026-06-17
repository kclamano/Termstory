from textual.app import App, ComposeResult
from textual.widgets import Label, Button, Tree
from textual import work
from textual.worker import get_current_worker
import asyncio
import time

class DebounceTestApp(App):
    def compose(self) -> ComposeResult:
        yield Button("Trigger Heavy AI Task", id="trigger")
        yield Label("Ready", id="status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.query_one("#status").update("Starting task...")
        self.heavy_ai_task()

    @work(thread=True, exclusive=True)
    def heavy_ai_task(self):
        worker = get_current_worker()
        for i in range(10):
            if worker.is_cancelled:
                self.call_from_thread(self.query_one("#status").update, "Task Cancelled!")
                return
            time.sleep(0.5)
            self.call_from_thread(self.query_one("#status").update, f"Working... {i*10}%")
        
        if not worker.is_cancelled:
            self.call_from_thread(self.query_one("#status").update, "Task Complete!")

if __name__ == "__main__":
    app = DebounceTestApp()
    print("Debounce test script created. To run: python3 poc_debounced_workers.py")
    # We will simulate the interactions programmatically.
