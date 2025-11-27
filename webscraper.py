"""Simple yet powerful web scraping utility with a Tkinter UI."""

from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue, Empty
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


@dataclass
class ScrapeResult:
    index: int
    text: str
    attr: Optional[str]
    snippet: str


class Scraper:
    timeout: int = 15

    def fetch(self, url: str) -> str:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def parse(
        self,
        html: str,
        selector: Optional[str],
        attr: Optional[str],
        scrape_all: bool = False,
    ) -> List[ScrapeResult]:
        soup = BeautifulSoup(html, "html.parser")
        if scrape_all:
            strings = [text.strip() for text in soup.stripped_strings if text.strip()]
            return [
                ScrapeResult(idx, text, "text", text[:100]) for idx, text in enumerate(strings, start=1)
            ]

        elements = soup.select(selector or "body *")
        results: List[ScrapeResult] = []
        for idx, el in enumerate(elements, start=1):
            value = el.get_text(strip=True) if attr == "text" else el.get(attr) or ""
            snippet = el.get_text(strip=True)[:100]
            results.append(ScrapeResult(idx, value, attr, snippet))
        return results

    def scrape(
        self,
        url: str,
        selector: Optional[str],
        attr: Optional[str],
        scrape_all: bool = False,
    ) -> List[ScrapeResult]:
        html = self.fetch(url)
        return self.parse(html, selector, attr, scrape_all=scrape_all)


class ScraperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Web Scraper")
        self.geometry("800x600")
        self.scraper = Scraper()
        self.result_queue: Queue = Queue()
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(frame, width=80)
        self.url_entry.grid(row=0, column=1, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="CSS Selector:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.selector_entry = ttk.Entry(frame, width=80)
        self.selector_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="Attribute:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.attr_combo = ttk.Combobox(frame, values=["text", "href", "src"], state="readonly")
        self.attr_combo.current(0)
        self.attr_combo.grid(row=2, column=1, sticky=tk.W, pady=5)

        self.scrape_all_var = tk.BooleanVar(value=False)
        self.scrape_all_check = ttk.Checkbutton(
            frame,
            text="Scrape entire page (ignore selector)",
            variable=self.scrape_all_var,
            command=self.toggle_selector_inputs,
        )
        self.scrape_all_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Scrape", command=self.start_scrape).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)

        columns = ("index", "value", "snippet")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        self.tree.heading("index", text="#")
        self.tree.heading("value", text="Value")
        self.tree.heading("snippet", text="Snippet")
        self.tree.column("index", width=50, anchor=tk.CENTER)
        self.tree.column("value", width=300)
        self.tree.column("snippet", width=300)
        self.tree.grid(row=5, column=0, columnspan=2, sticky=tk.NSEW)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var).pack(fill=tk.X, pady=5)

    def start_scrape(self):
        url = self.url_entry.get().strip()
        selector = self.selector_entry.get().strip()
        attr = self.attr_combo.get().strip()
        scrape_all = self.scrape_all_var.get()
        if not url:
            messagebox.showwarning("Missing Fields", "Please provide a URL.")
            return
        if not scrape_all and not selector:
            messagebox.showwarning("Missing Fields", "Please provide a CSS selector or enable full-page mode.")
            return

        self.status_var.set("Scraping...")
        threading.Thread(
            target=self._run_scrape,
            args=(url, selector or None, attr, scrape_all),
            daemon=True,
        ).start()
        self.after(100, self.check_queue)

    def _run_scrape(self, url, selector, attr, scrape_all):
        try:
            results = self.scraper.scrape(url, selector, attr, scrape_all=scrape_all)
            self.result_queue.put(("success", results))
        except Exception as e:
            self.result_queue.put(("error", str(e)))

    def check_queue(self):
        try:
            status, data = self.result_queue.get_nowait()
            if status == "success":
                self.populate_results(data)
                self.status_var.set(f"Scraped {len(data)} items.")
            else:
                messagebox.showerror("Error", data)
                self.status_var.set("Error occurred.")
        except Empty:
            self.after(100, self.check_queue)

    def populate_results(self, results: List[ScrapeResult]):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for res in results:
            self.tree.insert("", tk.END, values=(res.index, res.text, res.snippet))

    def export_csv(self):
        if not self.tree.get_children():
            messagebox.showinfo("No Data", "No scraped data to export.")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return
        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Index", "Value", "Snippet"])
            for item in self.tree.get_children():
                writer.writerow(self.tree.item(item)["values"])
        messagebox.showinfo("Exported", f"Data exported to {file_path}")

    def toggle_selector_inputs(self):
        disabled = self.scrape_all_var.get()
        state = "disabled" if disabled else "normal"
        self.selector_entry.configure(state=state)
        self.attr_combo.configure(state="disabled" if disabled else "readonly")


if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()

