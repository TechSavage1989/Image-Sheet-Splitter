"""PyInstaller hook for tkinterdnd2 / TkDnD runtime data."""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("tkinterdnd2")
