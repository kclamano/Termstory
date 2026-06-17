import pytest
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Label, Button
from textual import work
from textual.worker import get_current_worker
import time

class DebounceTestApp(App):
    def __init__(self):
        super().__init__()
        self.cancel_count = 0

    def compose(self) -> ComposeResult:
        yield Button("Trigger", id="trigger")
        yield Label("Ready", id="status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.heavy_ai_task()

    @work(thread=True, exclusive=True)
    def heavy_ai_task(self):
        worker = get_current_worker()
        for i in range(5):
            if worker.is_cancelled:
                self.cancel_count += 1
                return
            time.sleep(0.1)
        
        self.call_from_thread(self.query_one("#status").update, "Complete")

async def run_test():
    app = DebounceTestApp()
    async with app.run_test() as pilot:
        await pilot.click("#trigger")
        await asyncio.sleep(0.2)
        await pilot.click("#trigger")
        await asyncio.sleep(0.6)
        
        if app.cancel_count > 0:
            print("Debounce test passed successfully! Cancel count:", app.cancel_count)
        else:
            print("Failed: Worker was not cancelled.")

if __name__ == "__main__":
    asyncio.run(run_test())
