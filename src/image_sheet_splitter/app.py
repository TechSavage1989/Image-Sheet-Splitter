import json
import math
import os
import queue
import re
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from collections import Counter
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .paths import (
    default_config_path,
    downloads_dir,
    ensure_runtime_dirs,
    load_settings,
    resolve_config_path,
    staging_dir,
    write_config_locator as persist_config_locator,
)
from .runtime import mark_healthy, parse_runtime_args
from .updater import (
    CHECK_INTERVAL_SECONDS,
    FOCUS_RECHECK_SECONDS,
    MANUAL_COOLDOWN_SECONDS,
    UpdateManager,
)
from .version import APP_NAME, APP_USER_MODEL_ID, APP_VERSION, RELEASES_URL

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
    APP_TK_BASE = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False
    APP_TK_BASE = tk.Tk

ICON_ICO = "Image_Sheet_Splitter.ico"
ICON_PNG = "Image_Sheet_Splitter.png"

try:
    from PIL import Image, ImageChops
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Pillow is required",
        "This source version needs the Pillow image library.\n\n"
        "If you are building the portable EXE, use Build Portable EXE.bat."
    )
    raise SystemExit


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
DROP_HINT_DEFAULT = "Drop image files or folders here"
DROP_HINT_ACTIVE = "Release to add these images"

# Common Wii U Virtual Console artwork targets. These are only a naming
# profile: Image Sheet Splitter remains a universal sheet splitter.
# A crop must be exact or very close to a target before a descriptive VC name
# is assigned. All other crops receive neutral, dimension-based names.
VC_OUTPUT_PROFILES = (
    ((128, 128), "Icon.png"),
    ((854, 480), "Gamepad Image.png"),
    ((1280, 720), "TV Image.png"),
    ((170, 42), "Logo.png"),
)
VC_SIZE_TOLERANCE_RATIO = 0.02
VC_SIZE_MIN_TOLERANCE = 2
GENERATED_OUTPUT_PATTERNS = (
    "piece_*.png",          # legacy versions
    "Image_*.png",
    "Icon*.png",
    "Gamepad Image*.png",
    "TV Image*.png",
    "Logo*.png",
    "iconTex*.png",        # legacy VC names
    "bootDrcTex*.png",
    "bootTvTex*.png",
)


def vc_profile_name(width, height):
    """Return a VC descriptive filename when a crop is exact or very close.

    Matching is deliberately conservative so unrelated image sheets do not
    accidentally receive Virtual Console-specific names.
    """
    best = None
    for (target_w, target_h), filename in VC_OUTPUT_PROFILES:
        tol_w = max(VC_SIZE_MIN_TOLERANCE, int(math.ceil(target_w * VC_SIZE_TOLERANCE_RATIO)))
        tol_h = max(VC_SIZE_MIN_TOLERANCE, int(math.ceil(target_h * VC_SIZE_TOLERANCE_RATIO)))
        delta_w = abs(width - target_w)
        delta_h = abs(height - target_h)
        if delta_w <= tol_w and delta_h <= tol_h:
            score = (delta_w / target_w) + (delta_h / target_h)
            if best is None or score < best[0]:
                best = (score, filename)
    return best[1] if best else None


HELP_TOPICS = [
    (
        "Getting Started",
        "Getting Started",
        """QUICK START

1. Choose an output directory.
2. Add one or more image sheets with Add Image(s), Add Folder, or drag files/folders into the selection area.
3. Leave the default detection options in place for the first pass.
4. Click Split Images.
5. Review Results for detected images, saved files, and any errors.
6. Open the output folder and verify the extracted images.

WHAT THE APPLICATION DOES

Image Sheet Splitter finds individual images separated by a solid background color. It detects the most common border color, treats that as the separator background, and exports each detected region as a PNG.

The application is designed for batch processing. You can add several sheets at once, choose one output root, and let the application create a separate folder for each source sheet.

HOVER HELP

Most interactive controls provide brief hover hints. Rest the pointer over a control until it settles to see a short explanation. See the Hover Help topic for the exact dismissal behavior.

HELP

Press F1 at any time to open this Documentation Center. The Help menu also contains shortcuts that open specific topics directly.""",
    ),
    (
        "Selecting Sheets & Folders",
        "Selecting Sheets & Folders",
        """ADDING INDIVIDUAL FILES

Use File > Add Image(s), the Add Image(s) button, or drag supported image files from Windows Explorer into the selection area. Multiple files can be dropped at once.

Supported source formats:
- PNG
- JPEG / JPG
- BMP
- WebP

ADDING A FOLDER

Use File > Add Folder, the Add Folder button, or drag a folder into the selection area. The application reads supported images directly in the selected or dropped folder and does not recursively scan subfolders.

CLEARING THE LIST

Use Clear to remove all selected source sheets from the current batch. This does not delete or modify the original image files.""",
    ),
    (
        "Drag & Drop",
        "Drag & Drop",
        """DRAGGING FILES

Drag PNG, JPEG / JPG, BMP, or WebP files from Windows Explorer onto the selected-sheet list or the drop area below it. Multiple files can be dropped in one operation, including paths that contain spaces.

DRAGGING FOLDERS

Folders can also be dropped. Image Sheet Splitter scans the top level of each dropped folder for supported image files. Subfolders are not scanned automatically.

DUPLICATES AND UNSUPPORTED ITEMS

Files already present in the current batch are not added again. Unsupported files are ignored and reported in Results when appropriate.

OTHER INPUT METHODS

Drag and drop is optional. File > Add Image(s), File > Add Folder, and the matching main-window buttons remain available at all times.""",
    ),
    (
        "Output & Naming",
        "Output Directory & Export Naming",
        """OUTPUT DIRECTORY

Choose the output root from the main window. You can also define a default output directory in Settings > Settings > General. The most recently selected output directory is saved in the application configuration.

PER-SHEET FOLDERS

Each source sheet is exported into its own subfolder. The folder name is based on the source filename and is cleaned so it is safe to use as a Windows folder name.

OUTPUT NAMING

Image Sheet Splitter is a universal sprite-sheet utility. Most extracted images receive neutral filenames containing their sequence number and dimensions, such as Image_01_640x480.png.

For convenience, crops that exactly match or are very close to these Wii U Virtual Console artwork targets receive descriptive filenames:
- 128 x 128: Icon.png
- 854 x 480: Gamepad Image.png
- 1280 x 720: TV Image.png
- 170 x 42: Logo.png

The size match is intentionally conservative. Images outside the small tolerance are kept generic so unrelated image sheets are not mislabeled as Virtual Console artwork.

If the same recognized type appears more than once, the application adds a numeric suffix rather than overwriting an earlier image.""",
    ),
    (
        "Detection & Separator Settings",
        "Detection & Separator Settings",
        """BACKGROUND DETECTION

The application samples the outside border of the source image and selects the most common exact RGBA color as the separator background.

BACKGROUND TOLERANCE

Tolerance controls how different a pixel must be from the detected background before it is considered part of an image.

- Lower values are stricter and work well with perfectly solid separators.
- Higher values can help when compression, antialiasing, or slight color variation exists near the separators.
- Increasing tolerance too far can remove legitimate image detail or merge regions unexpectedly.

MINIMUM WIDTH AND HEIGHT

Minimum crop width and height filter out tiny detected regions. Raise these values if insignificant marks or artifacts are being exported as separate files.

RECOMMENDED TROUBLESHOOTING ORDER

1. Start with the defaults.
2. If valid pieces are missed, adjust tolerance gradually.
3. If tiny unwanted pieces are detected, raise the minimum width or height.
4. Re-run the sheet and compare Results.""",
    ),
    (
        "Results Panel",
        "Results Panel",
        """RESULTS

The Results panel is a compact activity area at the bottom of the main window. Its header shows whether live file logging is on or off and the currently selected output directory. The activity list shows file additions, output changes, detection counts, saved output files, warnings, and errors.

RESIZING RESULTS

Drag the horizontal splitter bar immediately above Results to give the panel more or less vertical space. The upper workspace and Results remain independently resizable while the main window is resized.

DETACHING

Use Detach or View > Detach Results to move Results into a separate resizable window. The detached window keeps the same activity content and logging-status information.

REATTACHING

Use Reattach in the detached window, close the detached Results window with the window close control, or choose View > Reattach Results. Existing result lines are retained.

CLOSING AND SHOWING

Use Close in the Results header to hide the panel without clearing its contents. Choose View > Show Results to display it again.

The Results panel is an in-application activity view. File logging is controlled separately in Settings.""",
    ),
    (
        "Resizable Layout",
        "Resizable Layout & Splitter Bars",
        """DRAGGABLE SPLITTERS

Image Sheet Splitter uses draggable splitter bars so the main areas can be resized without making controls inaccessible.

HORIZONTAL WORKSPACE SPLITTER

Drag the vertical splitter between Select image sheets and the processing controls to change how much width each side receives.

RESULTS SPLITTER

Drag the horizontal splitter above Results to change the height of the activity area.

RESETTING PANEL SIZES

Choose View > Reset Panel Sizes to return the main splitters to their default proportions.

If Results is hidden, choose View > Show Results. If Results is detached, choose View > Reattach Results to return it to the main window.""",
    ),
    (
        "Settings & Configuration",
        "Settings & Configuration",
        """OPENING SETTINGS

Choose Settings > Settings to configure application behavior.

GENERAL

General settings include the default output directory, whether the output folder opens after a successful split, and the location of the JSON configuration file.

DETECTION

Detection settings contain background tolerance and minimum crop dimensions. The same values are available on the main window for quick adjustment.

CONFIGURATION FILE

By default, the application keeps its configuration under the current user's local application-data folder. You can move the configuration to another JSON file from Settings > Settings > General.

A small locator file remains in the normal per-user application-data folder so Image Sheet Splitter can remember where the custom configuration file is stored.

Use Settings > Open Config Folder to open the folder containing the active configuration file.""",
    ),
    (
        "Activity Log & File Logging",
        "Activity Log & File Logging",
        """FILE LOGGING

File logging can be enabled or disabled in Settings > Settings > Logging. When enabled, Image Sheet Splitter writes activity live to a timestamped text log.

LOG DIRECTORY

The log output directory is configurable. Use Settings > Open Log Folder to open the configured location, or Settings > Open Current Log to open the active session log.

LOGGED ACTIVITY INCLUDES

- Application start and close events
- Configuration and logging status
- Files added to the batch
- Output-directory changes
- Split operations and detection results
- Saved output file paths
- Errors and warnings
- Results-panel detach and reattach events

Disabling file logging does not disable the on-screen Results panel.""",
    ),
    (
        "Updates",
        "Updates & Restart",
        """AUTOMATIC CHECKS

Image Sheet Splitter checks the stable GitHub release feed shortly after startup, every five minutes while active, and after the app returns to the foreground when at least two minutes have passed since the previous check. Checks use cached ETags when available.

NETWORK FAILURES

If the app is offline or the update service cannot be reached, Image Sheet Splitter reports that the latest version could not be verified. A failed check never reports the installed version as current. Throttling and Retry-After responses are respected with backoff.

MANUAL CHECK

Choose Help > Check for Updates to check immediately. Repeated manual checks have a short cooldown to avoid unnecessary requests.

DOWNLOADING

When an update is available, a compact banner shows the installed/latest versions and short What's new notes. Click Download to fetch and verify the update. Downloading never starts automatically.

INSTALL AND RESTART

After a download passes SHA-256, archive safety, application identity, and version checks, choose Install and restart. Installation is blocked while an image split is active. The current application closes only after you confirm.

ROLLBACK

The updater keeps one previous executable as a rollback backup. The new application must open a visible window and report healthy before the update helper accepts the install. If that health check fails, the previous executable is restored and relaunched.

SHA-256 NOTE

A matching SHA-256 confirms that the downloaded bytes match the release manifest. It does not prove publisher code signing.""",
    ),
    (
        "Troubleshooting",
        "Troubleshooting",
        """NO IMAGES ARE DETECTED

Confirm that the pieces are separated by a consistent background color. Try changing Background tolerance gradually. Very small regions may also be filtered by the minimum width and height settings.

TOO MANY SMALL IMAGES ARE EXPORTED

Increase Minimum width and/or Minimum height. If the source has noisy or slightly varied separator pixels, a modest tolerance increase may also help.

PIECES ARE MERGED TOGETHER

The splitter relies on full separator rows and columns. Confirm that a continuous background separator exists between the pieces. Reduce tolerance if legitimate separator pixels are being treated as foreground.

WRONG OUTPUT LOCATION

Choose the desired folder on the main screen or update the default in Settings. The current path is shown before the split begins.

NO LOG FILE IS CREATED

Open Settings > Settings > Logging and confirm Enable file logging is selected and the log directory is valid. The on-screen Results panel continues to work even when file logging is disabled.

APPLICATION WILL NOT START ON ANOTHER PC

Share the finished portable Image Sheet Splitter.exe produced by the build kit, not the Python source file. The portable EXE contains Python, Pillow, and the required runtime components.""",
    ),
    (
        "Hover Help",
        "Hover Help & Control Hints",
        """HOW HOVER HELP WORKS

Most interactive controls include a short explanation that appears when you rest the pointer over the control. Hover Help is designed to provide context without getting in the way of normal operation.

BEHAVIOR

1. A hint appears only after the pointer has settled over a supported control.
2. The hint closes automatically after enough time to read it.
3. Once visible, the hint closes if the pointer moves eight or more pixels.
4. The hint closes when you click, scroll, type, change focus, or leave the control.
5. After a hint is dismissed, it stays hidden until the pointer leaves and re-enters that control.
6. Only one hint can be displayed at a time.

USING HOVER HELP

Rest the pointer over buttons, path fields, detection controls, checkboxes, the Results panel, and other supported controls when you want a brief explanation. For more detailed information, press F1 to open the Documentation Center.""",
    ),
    (
        "Credits & Notices",
        "Credits & Notices",
        """Image Sheet Splitter is an independent utility for separating images from sprite and artwork sheets.

The portable Windows build includes the Python runtime, Tk/Tcl components, and the Pillow image library as collected by PyInstaller. Those projects remain subject to their respective licenses and notices.

Image Sheet Splitter does not include game artwork, ROM data, copyrighted image sheets, or content from third-party websites. Users are responsible for ensuring they have the right to process and redistribute source images and exported files.

Nintendo, Wii U, Virtual Console, and names of other third-party products or services are the property of their respective owners. References to common artwork dimensions are descriptive and do not imply affiliation or endorsement.

The Spriters Resource is a separate third-party website and is not affiliated with Image Sheet Splitter.""",
    ),
]


def resource_path(filename):
    """Return a resource path in source and PyInstaller one-file builds."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    source_assets = Path(__file__).resolve().parents[2] / "assets" / "icons" / filename
    if source_assets.exists():
        return str(source_assets)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def configure_windows_process():
    """Set Windows application identity and DPI behavior before Tk starts."""
    if not sys.platform.startswith("win"):
        return

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def bands(values):
    """Return inclusive-exclusive runs of nonzero entries."""
    out = []
    start = None
    for i, value in enumerate(values):
        if value and start is None:
            start = i
        elif not value and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(values)))
    return out


def detect_background(im):
    """Pick the most common exact RGBA color on the outer border."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()

    samples = []
    for x in range(w):
        samples.append(px[x, 0])
        if h > 1:
            samples.append(px[x, h - 1])
    for y in range(1, max(1, h - 1)):
        samples.append(px[0, y])
        if w > 1:
            samples.append(px[w - 1, y])

    return Counter(samples).most_common(1)[0][0]


def make_foreground_mask(im, bg, tolerance):
    rgba = im.convert("RGBA")
    bg_img = Image.new("RGBA", rgba.size, bg)
    diff = ImageChops.difference(rgba, bg_img)
    r, g, b, a = diff.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(b, a))
    return mx.point(lambda v: 255 if v > tolerance else 0, mode="1")


def find_rectangles(im, tolerance=8, min_width=8, min_height=8):
    """Split a sheet using full-background separator rows and columns."""
    bg = detect_background(im)
    mask = make_foreground_mask(im, bg, tolerance)

    _, yproj = mask.getprojection()
    ybands = bands(yproj)

    rects = []
    for y0, y1 in ybands:
        band_mask = mask.crop((0, y0, mask.width, y1))
        xproj, _ = band_mask.getprojection()
        xbands = bands(xproj)

        for x0, x1 in xbands:
            region = mask.crop((x0, y0, x1, y1))
            bbox = region.getbbox()
            if not bbox:
                continue
            bx0, by0, bx1, by1 = bbox
            rect = (x0 + bx0, y0 + by0, x0 + bx1, y0 + by1)

            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width >= min_width and height >= min_height:
                rects.append(rect)

    return bg, sorted(set(rects), key=lambda r: (r[1], r[0], r[3], r[2]))


def game_folder_name(path):
    stem = Path(path).stem.strip()
    candidate = stem.rsplit(" - ", 1)[-1].strip() if " - " in stem else stem
    candidate = re.sub(r"\s*_\s*", " - ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    bad = '<>:"/\\|?*'
    candidate = "".join("_" if c in bad else c for c in candidate).strip(" .")
    return candidate or "game"


class HoverHelpManager:
    """Centralized hover-help manager with delayed display and strict dismissal rules."""

    def __init__(self, root, delay_ms=700, movement_threshold=8):
        self.root = root
        self.delay_ms = int(delay_ms)
        self.movement_threshold = int(movement_threshold)
        self.states = {}
        self.hover_widget = None
        self.visible_widget = None
        self.tip_window = None
        self.show_after_id = None
        self.hide_after_id = None
        self.show_origin = None

        # Global user actions dismiss the current hint and keep it dismissed
        # until the pointer leaves and re-enters the hovered control.
        self.root.bind_all("<ButtonPress>", self._global_dismiss, add="+")
        self.root.bind_all("<MouseWheel>", self._global_dismiss, add="+")
        self.root.bind_all("<Button-4>", self._global_dismiss, add="+")
        self.root.bind_all("<Button-5>", self._global_dismiss, add="+")
        self.root.bind_all("<KeyPress>", self._global_dismiss, add="+")
        self.root.bind_all("<FocusIn>", self._focus_changed, add="+")

    def attach(self, widget, text):
        if not widget or not text:
            return widget

        self.states[widget] = {
            "text": str(text).strip(),
            "inside": False,
            "dismissed": False,
            "settle_x": 0,
            "settle_y": 0,
        }
        widget.bind("<Enter>", lambda event, w=widget: self._enter(w, event), add="+")
        widget.bind("<Motion>", lambda event, w=widget: self._motion(w, event), add="+")
        widget.bind("<Leave>", lambda event, w=widget: self._leave(w, event), add="+")
        widget.bind("<Destroy>", lambda event, w=widget: self._destroyed(w), add="+")
        return widget

    def _state(self, widget):
        return self.states.get(widget)

    def _enter(self, widget, event):
        state = self._state(widget)
        if state is None:
            return
        if self.hover_widget is not widget:
            self._cancel_show()
            self._hide_tip(mark_dismissed=False)
        self.hover_widget = widget
        state["inside"] = True
        state["dismissed"] = False
        state["settle_x"] = event.x_root
        state["settle_y"] = event.y_root
        self._schedule_show(widget)

    def _motion(self, widget, event):
        state = self._state(widget)
        if state is None or not state["inside"] or state["dismissed"]:
            return

        if self.visible_widget is widget and self.tip_window is not None:
            if self.show_origin is not None:
                dx = event.x_root - self.show_origin[0]
                dy = event.y_root - self.show_origin[1]
                if (dx * dx + dy * dy) >= (self.movement_threshold * self.movement_threshold):
                    self._dismiss_widget(widget)
            return

        # Before the hint appears, any pointer movement restarts the settle timer.
        state["settle_x"] = event.x_root
        state["settle_y"] = event.y_root
        self._schedule_show(widget)

    def _leave(self, widget, event=None):
        state = self._state(widget)
        if state is None:
            return
        state["inside"] = False
        state["dismissed"] = False
        self._cancel_show()
        if self.visible_widget is widget:
            self._hide_tip(mark_dismissed=False)
        if self.hover_widget is widget:
            self.hover_widget = None

    def _destroyed(self, widget):
        if self.hover_widget is widget:
            self.hover_widget = None
            self._cancel_show()
        if self.visible_widget is widget:
            self._hide_tip(mark_dismissed=False)
        self.states.pop(widget, None)

    def _schedule_show(self, widget):
        self._cancel_show()
        state = self._state(widget)
        if state is None or not state["inside"] or state["dismissed"]:
            return
        self.show_after_id = self.root.after(self.delay_ms, lambda w=widget: self._show(w))

    def _cancel_show(self):
        if self.show_after_id is not None:
            try:
                self.root.after_cancel(self.show_after_id)
            except tk.TclError:
                pass
            self.show_after_id = None

    def _cancel_hide(self):
        if self.hide_after_id is not None:
            try:
                self.root.after_cancel(self.hide_after_id)
            except tk.TclError:
                pass
            self.hide_after_id = None

    def _show(self, widget):
        self.show_after_id = None
        state = self._state(widget)
        if state is None or not state["inside"] or state["dismissed"]:
            return
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return

        self._hide_tip(mark_dismissed=False)

        tip = tk.Toplevel(self.root)
        tip.withdraw()
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass

        label = tk.Label(
            tip,
            text=state["text"],
            justify="left",
            anchor="w",
            wraplength=420,
            background="#ffffe1",
            foreground="#202020",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack()
        tip.update_idletasks()

        x = int(state["settle_x"]) + 16
        y = int(state["settle_y"]) + 22
        width = tip.winfo_reqwidth()
        height = tip.winfo_reqheight()
        screen_w = tip.winfo_screenwidth()
        screen_h = tip.winfo_screenheight()
        x = max(4, min(x, screen_w - width - 8))
        y = max(4, min(y, screen_h - height - 8))
        tip.geometry(f"+{x}+{y}")
        tip.deiconify()

        self.tip_window = tip
        self.visible_widget = widget
        self.show_origin = (int(state["settle_x"]), int(state["settle_y"]))

        # Scale display time to hint length so longer explanations remain readable.
        display_ms = max(4500, min(10000, 1400 + len(state["text"]) * 45))
        self.hide_after_id = self.root.after(display_ms, lambda w=widget: self._auto_dismiss(w))

    def _auto_dismiss(self, widget):
        self.hide_after_id = None
        if self.visible_widget is widget:
            self._dismiss_widget(widget)

    def _dismiss_widget(self, widget):
        state = self._state(widget)
        if state is not None and state["inside"]:
            state["dismissed"] = True
        self._cancel_show()
        self._hide_tip(mark_dismissed=False)

    def _hide_tip(self, mark_dismissed=False):
        self._cancel_hide()
        widget = self.visible_widget
        if mark_dismissed and widget is not None:
            state = self._state(widget)
            if state is not None and state["inside"]:
                state["dismissed"] = True
        if self.tip_window is not None:
            try:
                self.tip_window.destroy()
            except tk.TclError:
                pass
        self.tip_window = None
        self.visible_widget = None
        self.show_origin = None

    def _global_dismiss(self, event=None):
        widget = self.hover_widget or self.visible_widget
        if widget is not None:
            state = self._state(widget)
            if state is not None and state["inside"]:
                state["dismissed"] = True
        self._cancel_show()
        self._hide_tip(mark_dismissed=False)

    def _focus_changed(self, event=None):
        # Ignore focus movement inside the tooltip itself, which has no focusable controls.
        self._global_dismiss(event)


class App(APP_TK_BASE):
    def __init__(self, runtime_args=None):
        super().__init__()
        self.runtime_args = runtime_args or {}
        ensure_runtime_dirs()
        self.title(APP_NAME)
        self.geometry("980x700")
        self.minsize(760, 560)
        self.set_app_icon(self)

        self.files = []
        self.config_path = resolve_config_path()
        self.settings = load_settings(self.config_path)

        self.output_var = tk.StringVar(value=str(self.settings.get("output_dir", "")))
        self.tolerance_var = tk.IntVar(value=int(self.settings.get("tolerance", 8)))
        self.min_w_var = tk.IntVar(value=int(self.settings.get("min_width", 8)))
        self.min_h_var = tk.IntVar(value=int(self.settings.get("min_height", 8)))
        self.open_folder_var = tk.BooleanVar(value=bool(self.settings.get("open_export_folder", True)))
        self.logging_enabled = bool(self.settings.get("logging_enabled", True))
        self.log_dir = str(self.settings.get("log_dir", ""))

        self.result_lines = []
        self.results_window = None
        self.log_widget = None
        self.session_log_path = None
        self.documentation_window = None
        self.documentation_listbox = None
        self.documentation_text = None
        self.documentation_title_var = None
        self.documentation_current_topic = HELP_TOPICS[0][0]
        self.hover_help = HoverHelpManager(self)
        self.drag_drop_enabled = False
        self.is_processing = False
        self.update_manager = UpdateManager(APP_VERSION)
        self.update_queue = queue.Queue()
        self.update_info = None
        self.staged_update = None
        self.last_update_attempt = 0.0
        self.last_manual_update_check = 0.0
        self.window_was_foreground = False

        self.build_menu()
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<F1>", lambda event: self.open_documentation())

        self.save_config(silent=True)
        self.log_line(f"{APP_NAME} {APP_VERSION} started.")
        self.log_line(f"Configuration file: {self.config_path}")
        if self.logging_enabled:
            self.log_line(f"File logging enabled: {self.log_dir}")
        else:
            self.log_line("File logging disabled.", write_file=False)
        if self.drag_drop_enabled:
            self.log_line("Drag and drop input enabled.")
        else:
            self.log_line("Drag and drop is unavailable in this source run; file and folder selectors remain available.", level="WARN", write_file=False)

        self.after(1200, lambda: self.request_update_check(manual=False, reason="startup"))
        self.after(CHECK_INTERVAL_SECONDS * 1000, self.periodic_update_check)
        self.after(2500, self.monitor_window_focus)
        self.after(150, self.poll_update_queue)

        if self.runtime_args.get("post_update_health"):
            self.after(900, self.report_post_update_health)
        if self.runtime_args.get("rollback_message"):
            self.after(900, self.report_update_rollback)

    def set_app_icon(self, window):
        try:
            icon_file = resource_path(ICON_ICO)
            if os.path.exists(icon_file):
                window.iconbitmap(default=icon_file)
        except Exception:
            pass

        try:
            png_file = resource_path(ICON_PNG)
            if os.path.exists(png_file):
                if not hasattr(self, "_app_icon"):
                    self._app_icon = tk.PhotoImage(file=png_file)
                window.iconphoto(True, self._app_icon)
        except Exception:
            pass

    def build_menu(self):
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Add Image(s)...", command=self.add_files)
        file_menu.add_command(label="Add Folder...", command=self.add_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(label="Settings...", command=self.open_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="Open Config Folder", command=self.open_config_folder)
        settings_menu.add_command(label="Open Log Folder", command=self.open_log_folder)
        settings_menu.add_command(label="Open Current Log", command=self.open_current_log)
        menu_bar.add_cascade(label="Settings", menu=settings_menu)

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Show Results", command=self.show_results)
        view_menu.add_command(label="Hide Results", command=self.hide_results)
        view_menu.add_separator()
        view_menu.add_command(label="Detach Results", command=self.detach_results)
        view_menu.add_command(label="Reattach Results", command=self.reattach_results)
        view_menu.add_separator()
        view_menu.add_command(label="Reset Panel Sizes", command=self.reset_splitter_layout)
        menu_bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(
            label="Documentation Center",
            accelerator="F1",
            command=self.open_documentation,
        )
        help_menu.add_separator()
        for topic_label, _, _ in HELP_TOPICS:
            if topic_label == "Credits & Notices":
                continue
            help_menu.add_command(
                label=topic_label,
                command=lambda name=topic_label: self.open_documentation(name),
            )
        help_menu.add_separator()
        help_menu.add_command(
            label="Credits & Notices",
            command=lambda: self.open_documentation("Credits & Notices"),
        )
        help_menu.add_separator()
        help_menu.add_command(label="Check for Updates...", command=lambda: self.request_update_check(manual=True, reason="manual"))
        help_menu.add_command(label="View Releases", command=lambda: webbrowser.open(RELEASES_URL))
        help_menu.add_separator()
        help_menu.add_command(label="About Image Sheet Splitter", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu_bar)

    def build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            top,
            text="Batch-splits images packed on a solid separator background."
        ).pack(anchor="w", pady=(2, 0))

        self.update_banner = ttk.LabelFrame(self, text="Update available")
        banner_top = ttk.Frame(self.update_banner)
        banner_top.pack(fill="x", padx=8, pady=(6, 2))
        self.update_version_var = tk.StringVar(value="")
        ttk.Label(banner_top, textvariable=self.update_version_var, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.update_dismiss_btn = ttk.Button(banner_top, text="Close", command=self.hide_update_banner)
        self.update_dismiss_btn.pack(side="right")
        self.update_notes_var = tk.StringVar(value="")
        ttk.Label(self.update_banner, textvariable=self.update_notes_var, justify="left", wraplength=860).pack(fill="x", padx=8, pady=(0, 4))
        self.update_status_var = tk.StringVar(value="")
        ttk.Label(self.update_banner, textvariable=self.update_status_var, foreground="#555555").pack(fill="x", padx=8, pady=(0, 4))
        self.update_progress = ttk.Progressbar(self.update_banner, mode="determinate")
        self.update_button_row = ttk.Frame(self.update_banner)
        self.update_button_row.pack(fill="x", padx=8, pady=(0, 8))
        self.update_download_btn = ttk.Button(self.update_button_row, text="Download", command=self.download_selected_update)
        self.update_download_btn.pack(side="left")
        self.update_install_btn = ttk.Button(self.update_button_row, text="Install and restart", command=self.install_selected_update, state="disabled")
        self.update_install_btn.pack(side="left", padx=(6, 0))
        self.update_read_more_btn = ttk.Button(self.update_button_row, text="Read more", command=self.open_update_read_more)
        self.update_read_more_btn.pack(side="left", padx=(6, 0))
        self.hover_help.attach(self.update_download_btn, "Download and verify the selected update. The app will not install or restart until you explicitly choose Install and restart.")
        self.hover_help.attach(self.update_install_btn, "Install the already downloaded and verified update, then restart the app. This is blocked while an image split is active.")
        self.hover_help.attach(self.update_read_more_btn, "Open the GitHub release page for the available update.")
        self.hover_help.attach(self.update_dismiss_btn, "Hide this update banner. Future scheduled checks remain enabled.")

        # The main layout uses nested PanedWindow controls so the user can
        # resize the workspace and Results panel directly with visible sashes.
        self.main_paned = tk.PanedWindow(
            self,
            orient=tk.VERTICAL,
            sashwidth=7,
            sashrelief="raised",
            showhandle=True,
            handlesize=8,
            sashpad=1,
            opaqueresize=True,
            borderwidth=0,
            relief="flat",
        )
        self.main_paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.workspace_container = ttk.Frame(self.main_paned)
        self.results_container = ttk.Frame(self.main_paned)
        self.main_paned.add(self.workspace_container, minsize=300, stretch="always")
        self.main_paned.add(self.results_container, minsize=135, stretch="never")

        self.workspace_paned = tk.PanedWindow(
            self.workspace_container,
            orient=tk.HORIZONTAL,
            sashwidth=7,
            sashrelief="raised",
            showhandle=True,
            handlesize=8,
            sashpad=1,
            opaqueresize=True,
            borderwidth=0,
            relief="flat",
        )
        self.workspace_paned.pack(fill="both", expand=True)

        file_frame = ttk.LabelFrame(self.workspace_paned, text="1. Select image sheets")
        controls_frame = ttk.Frame(self.workspace_paned)
        self.workspace_paned.add(file_frame, minsize=285, stretch="always")
        self.workspace_paned.add(controls_frame, minsize=360, stretch="always")

        btns = ttk.Frame(file_frame)
        btns.pack(fill="x", padx=8, pady=8)
        add_images_btn = ttk.Button(btns, text="Add Image(s)...", command=self.add_files)
        add_images_btn.pack(side="left", padx=(0, 6))
        add_folder_btn = ttk.Button(btns, text="Add Folder...", command=self.add_folder)
        add_folder_btn.pack(side="left", padx=(0, 6))
        clear_btn = ttk.Button(btns, text="Clear", command=self.clear_files)
        clear_btn.pack(side="left")

        self.hover_help.attach(add_images_btn, "Select one or more sprite-sheet image files and add them to the current batch.")
        self.hover_help.attach(add_folder_btn, "Add supported image files from one folder. Subfolders are not scanned.")
        self.hover_help.attach(clear_btn, "Remove all selected sheets from the current batch. The original image files are not deleted.")

        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.listbox = tk.Listbox(list_frame, height=8)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=list_scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        self.hover_help.attach(
            self.listbox,
            "Image sheets currently queued for splitting. You can also drag supported image files or folders directly onto this list.",
        )

        self.drop_hint_var = tk.StringVar(value=DROP_HINT_DEFAULT)
        self.drop_zone = ttk.Label(
            file_frame,
            textvariable=self.drop_hint_var,
            anchor="center",
            relief="groove",
            padding=(8, 8),
        )
        self.drop_zone.pack(fill="x", padx=8, pady=(0, 5))
        self.hover_help.attach(
            self.drop_zone,
            "Drop PNG, JPEG / JPG, BMP, or WebP files here. You can also drop folders; the top level of each folder is scanned for supported images.",
        )

        workspace_hint = ttk.Label(
            file_frame,
            text="Drag the divider at the right edge to resize this area.",
        )
        workspace_hint.pack(anchor="w", padx=8, pady=(0, 6))

        self.setup_drag_and_drop(file_frame, self.listbox, self.drop_zone)

        out_frame = ttk.LabelFrame(controls_frame, text="2. Choose output directory")
        out_frame.pack(fill="x", padx=(6, 0), pady=(0, 6))
        output_entry = ttk.Entry(out_frame, textvariable=self.output_var)
        output_entry.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        output_browse_btn = ttk.Button(out_frame, text="Browse...", command=self.choose_output)
        output_browse_btn.pack(side="right", padx=8, pady=8)
        self.hover_help.attach(output_entry, "Root folder where extracted images will be saved. Type or paste a path here, or use Browse to select a folder.")
        self.hover_help.attach(output_browse_btn, "Choose the root output folder for the extracted images.")

        options = ttk.LabelFrame(controls_frame, text="3. Detection options")
        options.pack(fill="x", padx=(6, 0), pady=6)
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Background tolerance:").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=(8, 5))
        tolerance_spin = ttk.Spinbox(options, from_=0, to=80, width=8, textvariable=self.tolerance_var)
        tolerance_spin.grid(row=0, column=1, sticky="w", padx=4, pady=(8, 5))

        ttk.Label(options, text="Minimum width:").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=5)
        min_w_spin = ttk.Spinbox(options, from_=1, to=500, width=8, textvariable=self.min_w_var)
        min_w_spin.grid(row=1, column=1, sticky="w", padx=4, pady=5)

        ttk.Label(options, text="Minimum height:").grid(row=2, column=0, sticky="w", padx=(8, 4), pady=5)
        min_h_spin = ttk.Spinbox(options, from_=1, to=500, width=8, textvariable=self.min_h_var)
        min_h_spin.grid(row=2, column=1, sticky="w", padx=4, pady=5)

        open_output_check = ttk.Checkbutton(
            options, text="Open output folder when finished", variable=self.open_folder_var
        )
        open_output_check.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(5, 8))

        self.hover_help.attach(
            tolerance_spin,
            "Controls how different a pixel must be from the detected separator background before it is treated as image content. Lower values are stricter.",
        )
        self.hover_help.attach(min_w_spin, "Ignore detected regions narrower than this many pixels. Increase this value to filter small unwanted fragments.")
        self.hover_help.attach(min_h_spin, "Ignore detected regions shorter than this many pixels. Increase this value to filter small unwanted fragments.")
        self.hover_help.attach(open_output_check, "When enabled, Windows opens the selected output directory after a split finishes successfully.")

        action = ttk.LabelFrame(controls_frame, text="4. Process")
        action.pack(fill="x", padx=(6, 0), pady=(6, 0))
        action_row = ttk.Frame(action)
        action_row.pack(fill="x", padx=8, pady=8)
        self.split_btn = ttk.Button(action_row, text="Split Images", command=self.split_all)
        self.split_btn.pack(side="left")
        self.progress = ttk.Progressbar(action_row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.hover_help.attach(self.split_btn, "Process every selected image sheet using the current detection settings and save the extracted images to the output directory.")
        self.hover_help.attach(self.progress, "Shows progress through the selected image sheets during a split operation.")

        controls_hint = ttk.Label(
            controls_frame,
            text="Drag the divider at the left edge to resize the workspace sections.",
        )
        controls_hint.pack(anchor="w", padx=(12, 0), pady=(8, 0))

        results_header = ttk.Frame(self.results_container)
        results_header.pack(fill="x", padx=(0, 0), pady=(0, 2))
        ttk.Label(results_header, text="Results", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.close_results_btn = ttk.Button(results_header, text="Close", command=self.hide_results)
        self.close_results_btn.pack(side="right", padx=(6, 0))
        self.detach_btn = ttk.Button(results_header, text="Detach", command=self.detach_results)
        self.detach_btn.pack(side="right")
        self.hover_help.attach(self.detach_btn, "Move the Results panel into its own resizable window. Use Reattach to return it to the main window.")
        self.hover_help.attach(self.close_results_btn, "Hide the Results panel without clearing its contents. Use View > Show Results to display it again.")

        self.results_status_var = tk.StringVar()
        results_status = ttk.Label(self.results_container, textvariable=self.results_status_var)
        results_status.pack(fill="x", pady=(0, 4))
        self.hover_help.attach(results_status, "Shows whether file logging is enabled and which output directory is currently selected.")

        results_frame = ttk.Frame(self.results_container)
        results_frame.pack(fill="both", expand=True)
        self.embedded_log = tk.Text(results_frame, height=7, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.embedded_log.yview)
        self.embedded_log.configure(yscrollcommand=scroll.set)
        self.embedded_log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.log_widget = self.embedded_log
        self.hover_help.attach(
            self.embedded_log,
            "Session activity and split results appear here. Drag the horizontal divider above Results to resize this panel. File logging can be enabled or disabled independently in Settings.",
        )

        self.results_visible = True
        self.output_var.trace_add("write", self.update_results_status)
        self.update_results_status()
        self.after_idle(self.reset_splitter_layout)

    def format_ui_line(self, text, level):
        return f"{datetime.now().strftime('%H:%M:%S')}  {level:<7} {text}"

    def ensure_session_log(self):
        if not self.logging_enabled:
            return None
        if self.session_log_path is not None:
            return self.session_log_path
        if not self.log_dir:
            return None

        try:
            log_root = Path(self.log_dir).expanduser()
            log_root.mkdir(parents=True, exist_ok=True)
            filename = f"Image_Sheet_Splitter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.session_log_path = log_root / filename
            with self.session_log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{APP_NAME} {APP_VERSION}\n")
                fh.write(f"Session started: {datetime.now().isoformat(timespec='seconds')}\n\n")
            return self.session_log_path
        except OSError:
            self.session_log_path = None
            return None

    def write_log_file(self, text, level):
        path = self.ensure_session_log()
        if not path:
            return
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().isoformat(timespec='seconds')} [{level}] {text}\n")
        except OSError:
            pass

    def log_line(self, text, level="INFO", write_file=True):
        formatted = self.format_ui_line(text, level)
        self.result_lines.append(formatted)

        if self.log_widget is not None and self.log_widget.winfo_exists():
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", formatted + "\n")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")

        if write_file and self.logging_enabled:
            self.write_log_file(text, level)
        self.update_idletasks()

    def refresh_log_widget(self):
        if self.log_widget is None or not self.log_widget.winfo_exists():
            return
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        if self.result_lines:
            self.log_widget.insert("end", "\n".join(self.result_lines) + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def clear_results(self):
        self.result_lines.clear()
        self.refresh_log_widget()

    def update_results_status(self, *args):
        if not hasattr(self, "results_status_var"):
            return
        logging_text = "On" if self.logging_enabled else "Off"
        output = self.output_var.get().strip()
        output_text = f"Output: {output}" if output else "No output folder configured"
        self.results_status_var.set(f"Live file logging: {logging_text}    {output_text}")

    def _results_is_embedded(self):
        if not hasattr(self, "main_paned") or not hasattr(self, "results_container"):
            return False
        try:
            return any(str(pane) == str(self.results_container) for pane in self.main_paned.panes())
        except tk.TclError:
            return False

    def reset_splitter_layout(self):
        try:
            self.update_idletasks()
            workspace_width = max(1, self.workspace_paned.winfo_width())
            main_height = max(1, self.main_paned.winfo_height())
            if len(self.workspace_paned.panes()) >= 2:
                left_width = max(285, min(workspace_width - 360, int(workspace_width * 0.47)))
                self.workspace_paned.sash_place(0, left_width, 0)
            if self._results_is_embedded() and len(self.main_paned.panes()) >= 2:
                results_height = max(150, min(230, int(main_height * 0.30)))
                self.main_paned.sash_place(0, 0, max(300, main_height - results_height))
        except tk.TclError:
            pass

    def show_results(self):
        if self.results_window is not None and self.results_window.winfo_exists():
            self.results_window.deiconify()
            self.results_window.lift()
            self.results_visible = True
            return

        if not self._results_is_embedded():
            self.main_paned.add(self.results_container, minsize=135, stretch="never")
            self.after_idle(self._restore_results_split)
        self.log_widget = self.embedded_log
        self.results_visible = True
        self.refresh_log_widget()

    def _restore_results_split(self):
        try:
            self.update_idletasks()
            height = max(1, self.main_paned.winfo_height())
            if self._results_is_embedded() and len(self.main_paned.panes()) >= 2:
                self.main_paned.sash_place(0, 0, max(300, height - 190))
        except tk.TclError:
            pass

    def hide_results(self):
        if self.results_window is not None and self.results_window.winfo_exists():
            window = self.results_window
            self.results_window = None
            window.destroy()

        if self._results_is_embedded():
            try:
                self.main_paned.forget(self.results_container)
            except tk.TclError:
                pass

        self.log_widget = self.embedded_log
        self.results_visible = False
        self.refresh_log_widget()
        self.log_line("Results panel hidden.")

    def detach_results(self):
        if self.results_window is not None and self.results_window.winfo_exists():
            self.results_window.deiconify()
            self.results_window.lift()
            return

        if self._results_is_embedded():
            try:
                self.main_paned.forget(self.results_container)
            except tk.TclError:
                pass

        self.results_window = tk.Toplevel(self)
        self.results_window.title(f"{APP_NAME} - Results")
        self.results_window.geometry("900x320")
        self.results_window.minsize(520, 220)
        self.set_app_icon(self.results_window)
        self.results_window.protocol("WM_DELETE_WINDOW", self.reattach_results)

        header = ttk.Frame(self.results_window)
        header.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(header, text="Results", font=("Segoe UI", 10, "bold")).pack(side="left")
        close_btn = ttk.Button(header, text="Close", command=self.hide_results)
        close_btn.pack(side="right", padx=(6, 0))
        reattach_btn = ttk.Button(header, text="Reattach", command=self.reattach_results)
        reattach_btn.pack(side="right")
        self.hover_help.attach(reattach_btn, "Return this Results panel to the main Image Sheet Splitter window.")
        self.hover_help.attach(close_btn, "Close the detached Results panel without clearing its contents. Use View > Show Results to display it again.")

        status = ttk.Label(self.results_window, textvariable=self.results_status_var)
        status.pack(fill="x", padx=10, pady=(0, 4))
        self.hover_help.attach(status, "Shows whether file logging is enabled and which output directory is currently selected.")

        body = ttk.Frame(self.results_window)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        detached_log = tk.Text(body, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(body, orient="vertical", command=detached_log.yview)
        detached_log.configure(yscrollcommand=scroll.set)
        detached_log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.log_widget = detached_log
        self.results_visible = True
        self.hover_help.attach(detached_log, "Session activity and split results. Use Reattach to return this panel to the main window, or Close to hide it.")
        self.refresh_log_widget()
        self.log_line("Results panel detached.")

    def reattach_results(self):
        if self.results_window is not None and self.results_window.winfo_exists():
            window = self.results_window
            self.results_window = None
            window.destroy()

        self.log_widget = self.embedded_log
        if not self._results_is_embedded():
            self.main_paned.add(self.results_container, minsize=135, stretch="never")
            self.after_idle(self._restore_results_split)
        self.results_visible = True
        self.refresh_log_widget()
        self.log_line("Results panel reattached.")

    def setup_drag_and_drop(self, *widgets):
        """Register the source-selection area as a native file/folder drop target."""
        self.drag_drop_enabled = False
        if not DND_AVAILABLE:
            if hasattr(self, "drop_hint_var"):
                self.drop_hint_var.set("Drop support unavailable - use Add Image(s) or Add Folder")
            return

        registered = 0
        for widget in widgets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<DropEnter>>", self.on_drop_enter)
                widget.dnd_bind("<<DropLeave>>", self.on_drop_leave)
                widget.dnd_bind("<<Drop>>", self.on_drop)
                registered += 1
            except (tk.TclError, AttributeError):
                continue

        self.drag_drop_enabled = registered > 0
        if not self.drag_drop_enabled and hasattr(self, "drop_hint_var"):
            self.drop_hint_var.set("Drop support unavailable - use Add Image(s) or Add Folder")

    def on_drop_enter(self, event):
        if hasattr(self, "drop_hint_var"):
            self.drop_hint_var.set(DROP_HINT_ACTIVE)
        return getattr(event, "action", None)

    def on_drop_leave(self, event):
        if hasattr(self, "drop_hint_var"):
            self.drop_hint_var.set(DROP_HINT_DEFAULT)
        return getattr(event, "action", None)

    def collect_dropped_inputs(self, paths):
        """Expand dropped files/folders into supported image files without recursion."""
        images = []
        folder_count = 0
        skipped_inputs = 0
        empty_folders = 0

        for raw_path in paths:
            raw_path = str(raw_path).strip()
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            try:
                path = path.resolve()
            except OSError:
                path = Path(os.path.abspath(str(path)))

            if path.is_dir():
                folder_count += 1
                try:
                    matches = [
                        p for p in sorted(path.iterdir(), key=lambda p: p.name.lower())
                        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                    ]
                except OSError:
                    skipped_inputs += 1
                    continue
                if not matches:
                    empty_folders += 1
                images.extend(str(p) for p in matches)
            elif path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                images.append(str(path))
            else:
                skipped_inputs += 1

        return images, folder_count, skipped_inputs, empty_folders

    def on_drop(self, event):
        if hasattr(self, "drop_hint_var"):
            self.drop_hint_var.set(DROP_HINT_DEFAULT)

        try:
            dropped_paths = list(self.tk.splitlist(event.data))
        except (tk.TclError, TypeError):
            dropped_paths = [str(getattr(event, "data", ""))]

        images, folder_count, skipped, empty_folders = self.collect_dropped_inputs(dropped_paths)
        added, duplicates, rejected = self.add_paths(images, source="drag and drop")
        skipped += rejected

        if folder_count:
            self.log_line(f"Processed {folder_count} dropped folder(s).")
        if empty_folders:
            self.log_line(f"{empty_folders} dropped folder(s) contained no supported images.", level="WARN")
        if duplicates:
            self.log_line(f"Skipped {duplicates} duplicate image file(s) already in the batch.")
        if skipped:
            self.log_line(f"Ignored {skipped} unsupported or unavailable dropped item(s).", level="WARN")
        if not images and not skipped and not empty_folders:
            self.log_line("No supported image files were found in the dropped data.", level="WARN")

        return getattr(event, "action", None)

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select image sheets",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("PNG files", "*.png"),
                ("All files", "*.*"),
            ],
        )
        self.add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing image sheets")
        if not folder:
            return
        paths, _, _, _ = self.collect_dropped_inputs([folder])
        self.add_paths(paths)

    def add_paths(self, paths, source="selection"):
        existing = {os.path.normcase(os.path.abspath(path)) for path in self.files}
        added = 0
        duplicates = 0
        rejected = 0

        for raw_path in paths:
            path = os.path.abspath(str(raw_path))
            path_obj = Path(path)
            if not path_obj.is_file() or path_obj.suffix.lower() not in IMAGE_EXTS:
                rejected += 1
                continue

            normalized = os.path.normcase(path)
            if normalized in existing:
                duplicates += 1
                continue

            self.files.append(path)
            self.listbox.insert("end", path)
            existing.add(normalized)
            added += 1

        if added:
            if source == "drag and drop":
                self.log_line(f"Added {added} image file(s) by drag and drop.")
            else:
                self.log_line(f"Added {added} image file(s).")

        return added, duplicates, rejected

    def clear_files(self):
        count = len(self.files)
        self.files.clear()
        self.listbox.delete(0, "end")
        if count:
            self.log_line(f"Cleared {count} selected image file(s).")

    def choose_output(self):
        initial = self.output_var.get().strip() or None
        folder = filedialog.askdirectory(title="Choose output directory", initialdir=initial)
        if folder:
            old = self.output_var.get().strip()
            self.output_var.set(folder)
            self.settings["output_dir"] = folder
            self.save_config(silent=True)
            if folder != old:
                self.log_line(f"Output directory set to: {folder}")

    def collect_current_settings(self):
        try:
            tolerance = max(0, int(self.tolerance_var.get()))
            min_w = max(1, int(self.min_w_var.get()))
            min_h = max(1, int(self.min_h_var.get()))
        except (ValueError, tk.TclError):
            tolerance, min_w, min_h = 8, 8, 8
        return {
            "output_dir": self.output_var.get().strip(),
            "open_export_folder": bool(self.open_folder_var.get()),
            "tolerance": tolerance,
            "min_width": min_w,
            "min_height": min_h,
            "logging_enabled": bool(self.logging_enabled),
            "log_dir": self.log_dir,
        }

    def write_config_locator(self):
        persist_config_locator(self.config_path)

    def save_config(self, silent=False):
        self.settings = self.collect_current_settings()
        payload = dict(self.settings)
        payload["app_name"] = APP_NAME
        payload["app_version"] = APP_VERSION

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.write_config_locator()
            return True
        except OSError as exc:
            if not silent:
                messagebox.showerror(APP_NAME, f"Could not save the configuration file:\n\n{exc}")
            return False

    def open_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title(f"{APP_NAME} - Settings")
        dialog.geometry("700x430")
        dialog.minsize(640, 390)
        dialog.transient(self)
        dialog.grab_set()
        self.set_app_icon(dialog)

        temp_output = tk.StringVar(value=self.output_var.get())
        temp_open = tk.BooleanVar(value=self.open_folder_var.get())
        temp_tolerance = tk.IntVar(value=self.tolerance_var.get())
        temp_min_w = tk.IntVar(value=self.min_w_var.get())
        temp_min_h = tk.IntVar(value=self.min_h_var.get())
        temp_logging = tk.BooleanVar(value=self.logging_enabled)
        temp_log_dir = tk.StringVar(value=self.log_dir)
        temp_config = tk.StringVar(value=str(self.config_path))

        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        general = ttk.Frame(notebook)
        detection = ttk.Frame(notebook)
        logging_tab = ttk.Frame(notebook)
        notebook.add(general, text="General")
        notebook.add(detection, text="Detection")
        notebook.add(logging_tab, text="Logging")

        general.columnconfigure(1, weight=1)
        ttk.Label(general, text="Default output directory:").grid(row=0, column=0, sticky="w", padx=12, pady=(16, 8))
        default_output_entry = ttk.Entry(general, textvariable=temp_output)
        default_output_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=(16, 8))
        self.hover_help.attach(default_output_entry, "Default output directory used by the main window. You can type or paste a path here or choose Browse.")

        def browse_output_setting():
            folder = filedialog.askdirectory(title="Choose default output directory", initialdir=temp_output.get() or None, parent=dialog)
            if folder:
                temp_output.set(folder)

        default_output_browse = ttk.Button(general, text="Browse...", command=browse_output_setting)
        default_output_browse.grid(row=0, column=2, padx=(0, 12), pady=(16, 8))
        self.hover_help.attach(default_output_browse, "Choose the default output directory.")
        settings_open_output_check = ttk.Checkbutton(general, text="Open output folder when finished", variable=temp_open)
        settings_open_output_check.grid(row=1, column=1, sticky="w", padx=8, pady=8)
        self.hover_help.attach(settings_open_output_check, "Open the output folder automatically after a split finishes successfully.")

        ttk.Separator(general, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        ttk.Label(general, text="Configuration file:").grid(row=3, column=0, sticky="w", padx=12, pady=8)
        config_entry = ttk.Entry(general, textvariable=temp_config)
        config_entry.grid(row=3, column=1, sticky="ew", padx=8, pady=8)
        self.hover_help.attach(config_entry, "Location of the JSON configuration file used to store application settings. A small locator file remembers custom locations.")

        def browse_config_setting():
            current = Path(temp_config.get()).expanduser() if temp_config.get().strip() else default_config_path()
            selected = filedialog.asksaveasfilename(
                title="Choose configuration file",
                defaultextension=".json",
                initialdir=str(current.parent),
                initialfile=current.name,
                filetypes=[("JSON configuration", "*.json"), ("All files", "*.*")],
                parent=dialog,
            )
            if selected:
                temp_config.set(selected)

        config_browse_btn = ttk.Button(general, text="Browse...", command=browse_config_setting)
        config_browse_btn.grid(row=3, column=2, padx=(0, 12), pady=8)
        self.hover_help.attach(config_browse_btn, "Choose a JSON file location for the application configuration.")
        ttk.Label(
            general,
            text="Changing this location saves the current application settings to the selected JSON file.",
            foreground="#555555",
            wraplength=520,
        ).grid(row=4, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        detection.columnconfigure(1, weight=1)
        ttk.Label(detection, text="Background tolerance:").grid(row=0, column=0, sticky="w", padx=12, pady=(18, 10))
        settings_tolerance_spin = ttk.Spinbox(detection, from_=0, to=80, width=8, textvariable=temp_tolerance)
        settings_tolerance_spin.grid(row=0, column=1, sticky="w", padx=8, pady=(18, 10))
        self.hover_help.attach(settings_tolerance_spin, "Default separator-background tolerance. Lower values require a closer color match; higher values allow more variation.")
        ttk.Label(detection, text="Minimum crop width:").grid(row=1, column=0, sticky="w", padx=12, pady=10)
        settings_min_w_spin = ttk.Spinbox(detection, from_=1, to=500, width=8, textvariable=temp_min_w)
        settings_min_w_spin.grid(row=1, column=1, sticky="w", padx=8, pady=10)
        self.hover_help.attach(settings_min_w_spin, "Default minimum detected crop width. Regions narrower than this are ignored.")
        ttk.Label(detection, text="Minimum crop height:").grid(row=2, column=0, sticky="w", padx=12, pady=10)
        settings_min_h_spin = ttk.Spinbox(detection, from_=1, to=500, width=8, textvariable=temp_min_h)
        settings_min_h_spin.grid(row=2, column=1, sticky="w", padx=8, pady=10)
        self.hover_help.attach(settings_min_h_spin, "Default minimum detected crop height. Regions shorter than this are ignored.")

        logging_tab.columnconfigure(1, weight=1)
        enable_logging_check = ttk.Checkbutton(logging_tab, text="Enable file logging", variable=temp_logging)
        enable_logging_check.grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(18, 10))
        self.hover_help.attach(enable_logging_check, "Enable or disable writing session activity to timestamped log files. The on-screen Results panel remains available either way.")
        ttk.Label(logging_tab, text="Log output directory:").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        log_dir_entry = ttk.Entry(logging_tab, textvariable=temp_log_dir)
        log_dir_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        self.hover_help.attach(log_dir_entry, "Folder where timestamped log files are written when file logging is enabled.")

        def browse_log_setting():
            folder = filedialog.askdirectory(title="Choose log output directory", initialdir=temp_log_dir.get() or None, parent=dialog)
            if folder:
                temp_log_dir.set(folder)

        log_browse_btn = ttk.Button(logging_tab, text="Browse...", command=browse_log_setting)
        log_browse_btn.grid(row=1, column=2, padx=(0, 12), pady=8)
        self.hover_help.attach(log_browse_btn, "Choose the folder used for file logging.")
        ttk.Label(
            logging_tab,
            text="When enabled, activity is written live to a timestamped log file in this directory.",
            foreground="#555555",
            wraplength=520,
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def apply_settings():
            new_config_text = temp_config.get().strip()
            if not new_config_text:
                messagebox.showerror(APP_NAME, "Choose a configuration file location.", parent=dialog)
                return
            if temp_logging.get() and not temp_log_dir.get().strip():
                messagebox.showerror(APP_NAME, "Choose a log output directory or disable file logging.", parent=dialog)
                return

            try:
                tolerance = max(0, int(temp_tolerance.get()))
                min_w = max(1, int(temp_min_w.get()))
                min_h = max(1, int(temp_min_h.get()))
            except (ValueError, tk.TclError):
                messagebox.showerror(APP_NAME, "Detection values must be whole numbers.", parent=dialog)
                return

            old_config = self.config_path
            old_logging = self.logging_enabled
            old_log_dir = self.log_dir

            self.output_var.set(temp_output.get().strip())
            self.open_folder_var.set(bool(temp_open.get()))
            self.tolerance_var.set(tolerance)
            self.min_w_var.set(min_w)
            self.min_h_var.set(min_h)
            self.logging_enabled = bool(temp_logging.get())
            self.log_dir = temp_log_dir.get().strip()
            self.config_path = Path(new_config_text).expanduser()
            self.update_results_status()

            if old_logging and not self.logging_enabled:
                self.write_log_file("File logging disabled from Settings.", "INFO")
            if self.logging_enabled and (not old_logging or self.log_dir != old_log_dir):
                self.session_log_path = None

            if not self.save_config(silent=False):
                self.config_path = old_config
                return

            if self.config_path != old_config:
                self.log_line(f"Configuration file changed to: {self.config_path}")
            self.log_line("Settings saved.", write_file=self.logging_enabled)
            if self.logging_enabled:
                self.log_line(f"File logging enabled: {self.log_dir}")
            else:
                self.log_line("File logging disabled.", write_file=False)
            dialog.destroy()

        cancel_settings_btn = ttk.Button(buttons, text="Cancel", command=dialog.destroy)
        cancel_settings_btn.pack(side="right")
        save_settings_btn = ttk.Button(buttons, text="Save", command=apply_settings)
        save_settings_btn.pack(side="right", padx=(0, 8))
        self.hover_help.attach(cancel_settings_btn, "Close Settings without applying the changes made in this dialog.")
        self.hover_help.attach(save_settings_btn, "Apply these settings and save them to the configured JSON configuration file.")

    def open_path(self, path):
        try:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True) if not path.suffix else None
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open the requested location:\n\n{exc}")

    def open_config_folder(self):
        self.open_path(self.config_path.parent)

    def open_log_folder(self):
        if not self.log_dir:
            messagebox.showinfo(APP_NAME, "No log output directory is configured.")
            return
        self.open_path(Path(self.log_dir).expanduser())

    def open_current_log(self):
        path = self.ensure_session_log() if self.logging_enabled else self.session_log_path
        if not path or not Path(path).exists():
            messagebox.showinfo(APP_NAME, "There is no current log file to open.")
            return
        self.open_path(path)

    def get_help_topic(self, topic_name):
        for label, title, body in HELP_TOPICS:
            if label == topic_name:
                return label, title, body
        return HELP_TOPICS[0]

    def render_documentation_topic(self, topic_name):
        if self.documentation_text is None or not self.documentation_text.winfo_exists():
            return

        label, title, body = self.get_help_topic(topic_name)
        self.documentation_current_topic = label
        if self.documentation_title_var is not None:
            self.documentation_title_var.set(title)

        widget = self.documentation_text
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        for raw_line in body.splitlines():
            line = raw_line.rstrip()
            if not line:
                widget.insert("end", "\n")
            elif line.startswith("- ") and line[2:].strip() in {"PNG", "JPEG / JPG", "BMP", "WebP"}:
                widget.insert("end", line + "\n", "source_format")
            elif line.isupper() and len(line) <= 60:
                widget.insert("end", line + "\n", "section")
            elif re.match(r"^\d+\.\s", line):
                widget.insert("end", line + "\n", "numbered")
            elif line.startswith("- "):
                widget.insert("end", "• " + line[2:].strip() + "\n", "bullet")
            else:
                widget.insert("end", line + "\n", "body")

        widget.configure(state="disabled")
        widget.yview_moveto(0.0)

    def select_documentation_topic(self, topic_name):
        if self.documentation_listbox is None or not self.documentation_listbox.winfo_exists():
            return

        for index, (label, _, _) in enumerate(HELP_TOPICS):
            if label == topic_name:
                self.documentation_listbox.selection_clear(0, "end")
                self.documentation_listbox.selection_set(index)
                self.documentation_listbox.activate(index)
                self.documentation_listbox.see(index)
                self.render_documentation_topic(label)
                return

        self.documentation_listbox.selection_clear(0, "end")
        self.documentation_listbox.selection_set(0)
        self.documentation_listbox.activate(0)
        self.render_documentation_topic(HELP_TOPICS[0][0])

    def copy_documentation_topic(self):
        label, title, body = self.get_help_topic(self.documentation_current_topic)
        try:
            self.clipboard_clear()
            self.clipboard_append(f"{title}\n\n{body}")
            self.update_idletasks()
            self.log_line(f"Copied documentation topic: {label}")
        except tk.TclError:
            pass

    def open_documentation(self, topic=None):
        topic = topic or self.documentation_current_topic or HELP_TOPICS[0][0]

        if self.documentation_window is not None and self.documentation_window.winfo_exists():
            self.documentation_window.deiconify()
            self.documentation_window.lift()
            self.documentation_window.focus_force()
            self.select_documentation_topic(topic)
            return

        window = tk.Toplevel(self)
        self.documentation_window = window
        window.title(f"{APP_NAME} Documentation")
        window.geometry("980x720")
        window.minsize(760, 520)
        self.set_app_icon(window)

        def close_documentation():
            self.documentation_window = None
            self.documentation_listbox = None
            self.documentation_text = None
            self.documentation_title_var = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_documentation)

        header = ttk.Frame(window)
        header.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Label(
            header,
            text=f"{APP_NAME} Documentation",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")
        ttk.Label(header, text=f"v{APP_VERSION}").pack(side="left", padx=(14, 0), pady=(5, 0))

        main = ttk.Frame(window)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        nav = ttk.Frame(main)
        nav.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        ttk.Label(nav, text="Topics", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

        nav_frame = ttk.Frame(nav)
        nav_frame.pack(fill="y", expand=True)
        topic_list = tk.Listbox(
            nav_frame,
            width=29,
            height=24,
            exportselection=False,
            activestyle="none",
        )
        nav_scroll = ttk.Scrollbar(nav_frame, orient="vertical", command=topic_list.yview)
        topic_list.configure(yscrollcommand=nav_scroll.set)
        topic_list.pack(side="left", fill="y", expand=True)
        nav_scroll.pack(side="right", fill="y")
        for label, _, _ in HELP_TOPICS:
            topic_list.insert("end", label)
        self.documentation_listbox = topic_list
        self.hover_help.attach(topic_list, "Select a documentation topic to display it in the pane on the right.")

        content = ttk.Frame(main)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        self.documentation_title_var = tk.StringVar()
        ttk.Label(
            content,
            textvariable=self.documentation_title_var,
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        text_frame = ttk.Frame(content)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        doc_text = tk.Text(
            text_frame,
            wrap="word",
            state="disabled",
            padx=20,
            pady=16,
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 10),
        )
        doc_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=doc_text.yview)
        doc_text.configure(yscrollcommand=doc_scroll.set)
        doc_text.grid(row=0, column=0, sticky="nsew")
        doc_scroll.grid(row=0, column=1, sticky="ns")

        doc_text.tag_configure("section", font=("Segoe UI", 10, "bold"), foreground="#365b9d", spacing1=8, spacing3=4)
        doc_text.tag_configure("body", lmargin1=2, lmargin2=2, spacing3=2)
        doc_text.tag_configure("numbered", lmargin1=4, lmargin2=24, spacing3=2)
        doc_text.tag_configure("bullet", lmargin1=8, lmargin2=24, spacing3=2)
        doc_text.tag_configure("source_format", font=("Segoe UI", 10, "bold"), foreground="#365b9d", lmargin1=8, lmargin2=24, spacing3=2)
        self.documentation_text = doc_text
        self.hover_help.attach(doc_text, "Detailed help for the selected topic. Use the mouse wheel or scrollbar to move through longer topics.")

        def on_topic_selected(event=None):
            selection = topic_list.curselection()
            if not selection:
                return
            self.render_documentation_topic(HELP_TOPICS[selection[0]][0])

        topic_list.bind("<<ListboxSelect>>", on_topic_selected)

        footer = ttk.Frame(window)
        footer.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Label(
            footer,
            text="F1 opens this Documentation Center from anywhere in the application.",
            foreground="#555555",
        ).pack(side="left")
        close_docs_btn = ttk.Button(footer, text="Close", command=close_documentation)
        close_docs_btn.pack(side="right")
        copy_topic_btn = ttk.Button(footer, text="Copy Topic", command=self.copy_documentation_topic)
        copy_topic_btn.pack(side="right", padx=(0, 8))
        self.hover_help.attach(close_docs_btn, "Close the Documentation Center.")
        self.hover_help.attach(copy_topic_btn, "Copy the title and full text of the currently selected documentation topic to the Windows clipboard.")

        self.select_documentation_topic(topic)
        self.log_line(f"Opened documentation: {self.documentation_current_topic}")

    def hide_update_banner(self):
        try:
            self.update_banner.pack_forget()
        except tk.TclError:
            pass

    def show_update_banner(self, result):
        self.update_info = result
        self.update_version_var.set(
            f"Installed {result.installed_version}    Latest {result.latest_version}"
        )
        notes = list(result.notes or ())
        self.update_notes_var.set("\n".join(f"• {item}" for item in notes[:4]))
        self.update_status_var.set("Save active work before installing. Download and restart are always manual.")
        self.update_download_btn.configure(state="normal")
        self.update_install_button_state()
        if result.read_more_url:
            if not self.update_read_more_btn.winfo_manager():
                self.update_read_more_btn.pack(side="left", padx=(6, 0))
        else:
            self.update_read_more_btn.pack_forget()
        if not self.update_banner.winfo_manager():
            self.update_banner.pack(fill="x", padx=10, pady=(0, 6), before=self.main_paned)

    def update_install_button_state(self):
        if not hasattr(self, "update_install_btn"):
            return
        enabled = bool(self.staged_update) and not self.is_processing
        self.update_install_btn.configure(state="normal" if enabled else "disabled")

    def request_update_check(self, manual=False, reason="scheduled"):
        now = time.monotonic()
        if manual:
            elapsed = now - self.last_manual_update_check
            if self.last_manual_update_check and elapsed < MANUAL_COOLDOWN_SECONDS:
                remaining = max(1, int(MANUAL_COOLDOWN_SECONDS - elapsed))
                messagebox.showinfo(APP_NAME, f"Please wait about {remaining} seconds before checking again.", parent=self)
                return
            self.last_manual_update_check = now
        if self.update_manager.inflight:
            if manual:
                messagebox.showinfo(APP_NAME, "An update check is already running.", parent=self)
            return
        self.last_update_attempt = now
        if manual:
            self.log_line("Checking for updates manually.")
        thread = threading.Thread(
            target=self._update_check_worker,
            args=(manual, reason),
            name="ImageSheetSplitter-UpdateCheck",
            daemon=True,
        )
        thread.start()

    def _update_check_worker(self, manual, reason):
        try:
            result = self.update_manager.check(manual=manual)
            self.update_queue.put(("check", result, manual, reason))
        except Exception as exc:
            self.update_queue.put(("check_error", str(exc), manual, reason))

    def periodic_update_check(self):
        try:
            if time.monotonic() - self.last_update_attempt >= CHECK_INTERVAL_SECONDS:
                self.request_update_check(manual=False, reason="periodic")
        finally:
            self.after(CHECK_INTERVAL_SECONDS * 1000, self.periodic_update_check)

    def _is_window_foreground(self):
        if sys.platform.startswith("win"):
            try:
                import ctypes
                hwnd = int(self.winfo_id())
                root_hwnd = int(ctypes.windll.user32.GetAncestor(hwnd, 2)) or hwnd
                foreground = int(ctypes.windll.user32.GetForegroundWindow())
                return foreground in (hwnd, root_hwnd)
            except Exception:
                pass
        try:
            return self.focus_displayof() is not None
        except tk.TclError:
            return False

    def monitor_window_focus(self):
        try:
            foreground = self._is_window_foreground()
            if foreground and not self.window_was_foreground:
                if time.monotonic() - self.last_update_attempt >= FOCUS_RECHECK_SECONDS:
                    self.request_update_check(manual=False, reason="focus")
            self.window_was_foreground = foreground
        finally:
            self.after(1000, self.monitor_window_focus)

    def poll_update_queue(self):
        try:
            while True:
                event = self.update_queue.get_nowait()
                kind = event[0]
                if kind == "check":
                    _, result, manual, reason = event
                    self.handle_update_result(result, manual=manual, reason=reason)
                elif kind == "check_error":
                    _, message, manual, _reason = event
                    self.log_line(f"Update check error: {message}", level="WARN")
                    if manual:
                        messagebox.showwarning(APP_NAME, f"Unable to check for updates.\n\n{message}", parent=self)
                elif kind == "download_progress":
                    _, received, total = event
                    self.update_download_progress(received, total)
                elif kind == "download_done":
                    _, staged = event
                    self.staged_update = staged
                    self.update_progress.pack_forget()
                    self.update_status_var.set(
                        f"Downloaded and verified {staged['version']}. Choose Install and restart when ready."
                    )
                    self.update_download_btn.configure(state="disabled")
                    self.update_install_button_state()
                    self.log_line(f"Update {staged['version']} downloaded and verified.")
                elif kind == "download_error":
                    _, message = event
                    self.update_progress.pack_forget()
                    self.update_status_var.set(f"Download failed: {message}")
                    self.update_download_btn.configure(state="normal")
                    self.log_line(f"Update download failed: {message}", level="ERROR")
                    messagebox.showerror(APP_NAME, f"The update could not be downloaded or verified.\n\n{message}", parent=self)
        except queue.Empty:
            pass
        finally:
            self.after(150, self.poll_update_queue)

    def handle_update_result(self, result, manual=False, reason=""):
        if result.status == "available":
            self.show_update_banner(result)
            self.log_line(f"Update available: {result.latest_version} (installed {result.installed_version}).")
            return
        if result.status == "current":
            if manual:
                messagebox.showinfo(APP_NAME, result.message, parent=self)
            return
        if result.status == "no_release":
            if manual:
                messagebox.showinfo(APP_NAME, result.message, parent=self)
            return
        if result.status in ("error", "throttled"):
            self.log_line(f"Update check {result.status}: {result.message}", level="WARN", write_file=False)
            if manual:
                messagebox.showwarning(APP_NAME, result.message, parent=self)
            return
        if result.status == "busy" and manual:
            messagebox.showinfo(APP_NAME, result.message, parent=self)

    def open_update_read_more(self):
        if self.update_info and self.update_info.read_more_url:
            webbrowser.open(self.update_info.read_more_url)

    def download_selected_update(self):
        if not self.update_info or not self.update_info.available:
            return
        self.update_download_btn.configure(state="disabled")
        self.update_status_var.set("Downloading and verifying the update...")
        if not self.update_progress.winfo_manager():
            self.update_progress.pack(fill="x", padx=8, pady=(0, 6), before=self.update_button_row)
        self.update_progress.configure(value=0, maximum=max(1, self.update_info.asset_size))
        thread = threading.Thread(
            target=self._download_update_worker,
            name="ImageSheetSplitter-UpdateDownload",
            daemon=True,
        )
        thread.start()

    def _download_update_worker(self):
        try:
            staged = self.update_manager.download_and_stage(
                self.update_info,
                progress=lambda received, total: self.update_queue.put(("download_progress", received, total)),
            )
            self.update_queue.put(("download_done", staged))
        except Exception as exc:
            self.update_queue.put(("download_error", str(exc)))

    def update_download_progress(self, received, total):
        maximum = max(1, int(total or received or 1))
        self.update_progress.configure(maximum=maximum, value=min(received, maximum))
        if total:
            percent = min(100.0, (received / total) * 100.0)
            self.update_status_var.set(f"Downloading and verifying update... {percent:.0f}%")
        else:
            self.update_status_var.set(f"Downloading and verifying update... {received // 1024} KB")

    def install_selected_update(self):
        if self.is_processing:
            messagebox.showwarning(
                APP_NAME,
                "An image split is currently active. Finish the operation before installing the update.",
                parent=self,
            )
            return
        if not self.staged_update:
            return
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                APP_NAME,
                "Install and restart is available from the packaged Windows executable. Source runs can check and download, but they are not replaced in place.",
                parent=self,
            )
            return
        if not messagebox.askokcancel(
            APP_NAME,
            "Save any work in other applications if needed. Image Sheet Splitter will close, install the verified update, and restart.\n\nContinue?",
            parent=self,
        ):
            return
        if not self.save_config(silent=False):
            return
        try:
            plan = self.update_manager.make_install_plan(self.staged_update)
            self.update_manager.launch_install_helper(plan)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The update could not be started.\n\n{exc}", parent=self)
            self.log_line(f"Update install launch failed: {exc}", level="ERROR")
            return
        self.log_line(f"Installing update {self.staged_update['version']} and restarting.")
        self.after(100, self.destroy)

    def report_post_update_health(self):
        marker = self.runtime_args.get("post_update_health")
        from_version = self.runtime_args.get("post_update_from")
        try:
            self.update_idletasks()
            healthy = bool(self.winfo_viewable()) and mark_healthy(
                marker, APP_VERSION, self.runtime_args.get("post_update_token")
            )
        except tk.TclError:
            healthy = False
        if healthy:
            self.log_line(f"Updated successfully from {from_version or 'an earlier version'} to {APP_VERSION}.")
            messagebox.showinfo(APP_NAME, f"Update installed successfully.\n\nCurrent version: {APP_VERSION}", parent=self)
            self.after(3000, self.cleanup_post_update_files)
        else:
            self.log_line("Post-update health marker could not be written.", level="WARN")

    def _process_is_running(self, pid):
        if not pid:
            return False
        if sys.platform.startswith("win"):
            try:
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                STILL_ACTIVE = 259
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
                if not handle:
                    return False
                code = ctypes.c_ulong()
                try:
                    if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                        return False
                    return code.value == STILL_ACTIVE
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                return False
        return False

    def cleanup_post_update_files(self):
        plan_text = self.runtime_args.get("post_update_plan")
        if not plan_text:
            return
        plan_path = Path(plan_text)
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return
        helper_pid = plan.get("helper_pid")
        if self._process_is_running(helper_pid):
            self.after(1500, self.cleanup_post_update_files)
            return

        stage_root = Path(str(plan.get("stage_root", "")))
        archive = Path(str(plan.get("archive", "")))
        health = Path(str(plan.get("health_marker", "")))
        safe_stage = staging_dir().resolve()
        safe_downloads = downloads_dir().resolve()
        try:
            if stage_root and stage_root.resolve().is_relative_to(safe_stage):
                import shutil
                shutil.rmtree(stage_root, ignore_errors=True)
        except (OSError, ValueError):
            pass
        try:
            if archive and archive.resolve().is_relative_to(safe_downloads):
                archive.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        try:
            if health and health.resolve().is_relative_to(safe_stage):
                health.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        try:
            if plan_path.resolve().is_relative_to(safe_stage):
                plan_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        self.runtime_args["post_update_plan"] = None

    def report_update_rollback(self):
        message = self.runtime_args.get("rollback_message") or "The update did not complete successfully."
        self.log_line(f"Update rolled back: {message}", level="ERROR")
        messagebox.showerror(
            APP_NAME,
            "The update was rolled back and the previous application was restored.\n\n" + message,
            parent=self,
        )

    def show_about(self):
        dialog = tk.Toplevel(self)
        dialog.title(f"About {APP_NAME}")
        dialog.geometry("620x540")
        dialog.minsize(560, 470)
        dialog.transient(self)
        dialog.grab_set()
        self.set_app_icon(dialog)

        ttk.Label(
            dialog,
            text=APP_NAME,
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(24, 2))
        ttk.Label(dialog, text=f"Version {APP_VERSION}").pack()
        ttk.Label(
            dialog,
            text="A Windows utility for separating individual images from sprite and artwork sheets that use a solid separator background.",
            wraplength=560,
            justify="center",
        ).pack(padx=20, pady=(16, 12))

        body_frame = ttk.Frame(dialog)
        body_frame.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        body_frame.columnconfigure(0, weight=1)
        body_frame.rowconfigure(0, weight=1)

        about_text = tk.Text(
            body_frame,
            wrap="word",
            padx=10,
            pady=8,
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        about_scroll = ttk.Scrollbar(body_frame, orient="vertical", command=about_text.yview)
        about_text.configure(yscrollcommand=about_scroll.set)
        about_text.grid(row=0, column=0, sticky="nsew")
        about_scroll.grid(row=0, column=1, sticky="ns")

        _, _, notices = self.get_help_topic("Credits & Notices")
        about_text.insert(
            "1.0",
            f"{APP_NAME} is an independent utility and is not affiliated with or endorsed by Nintendo, The Spriters Resource, or other third-party content providers.\n\n"
            + notices
            + "\n\nPortable builds package the application with the Python runtime and Pillow so the finished EXE can run without a separate Python installation.",
        )
        about_text.configure(state="disabled")

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=18, pady=(0, 16))

        def open_docs_from_about():
            dialog.destroy()
            self.open_documentation("Getting Started")

        about_docs_btn = ttk.Button(buttons, text="Open Documentation", command=open_docs_from_about)
        about_docs_btn.pack(side="left")
        about_close_btn = ttk.Button(buttons, text="Close", command=dialog.destroy)
        about_close_btn.pack(side="right")
        self.hover_help.attach(about_docs_btn, "Close this About window and open the Documentation Center at Getting Started.")
        self.hover_help.attach(about_close_btn, "Close the About window.")

        self.log_line("Opened About dialog.")

    def split_all(self):
        if not self.files:
            messagebox.showwarning("No images selected", "Add at least one image sheet first.")
            return

        output_root = self.output_var.get().strip()
        if not output_root:
            output_root = filedialog.askdirectory(title="Choose output directory")
            if not output_root:
                return
            self.output_var.set(output_root)

        try:
            tolerance = max(0, int(self.tolerance_var.get()))
            min_w = max(1, int(self.min_w_var.get()))
            min_h = max(1, int(self.min_h_var.get()))
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid options", "Tolerance and minimum sizes must be whole numbers.")
            return

        output_root = Path(output_root)
        try:
            output_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not create the output directory:\n\n{exc}")
            return

        self.settings["output_dir"] = str(output_root)
        self.save_config(silent=True)

        self.is_processing = True
        self.split_btn.configure(state="disabled")
        self.update_install_button_state()
        self.progress["maximum"] = len(self.files)
        self.progress["value"] = 0
        total_pieces = 0
        failures = []

        self.clear_results()
        self.log_line(
            f"Starting split: {len(self.files)} sheet(s), output={output_root}, "
            f"tolerance={tolerance}, min={min_w}x{min_h}."
        )

        try:
            for index, src in enumerate(self.files, start=1):
                try:
                    with Image.open(src) as im:
                        im.load()
                        bg, rects = find_rectangles(
                            im,
                            tolerance=tolerance,
                            min_width=min_w,
                            min_height=min_h,
                        )

                        out_dir = output_root / game_folder_name(src)
                        out_dir.mkdir(parents=True, exist_ok=True)

                        # Remove files generated by earlier runs of this application so
                        # reduced/changed detection results do not leave stale outputs behind.
                        for pattern in GENERATED_OUTPUT_PATTERNS:
                            for old in out_dir.glob(pattern):
                                try:
                                    old.unlink()
                                except OSError:
                                    pass

                        used_names = set()
                        generic_number = 0
                        for number, rect in enumerate(rects, start=1):
                            crop = im.crop(rect)
                            width, height = crop.size
                            preferred = vc_profile_name(width, height)

                            if preferred:
                                name = preferred
                                if name.lower() in used_names:
                                    stem = Path(preferred).stem
                                    suffix = Path(preferred).suffix
                                    duplicate = 2
                                    while f"{stem}_{duplicate}{suffix}".lower() in used_names:
                                        duplicate += 1
                                    name = f"{stem}_{duplicate}{suffix}"
                            else:
                                generic_number += 1
                                name = f"Image_{generic_number:02d}_{width}x{height}.png"

                            used_names.add(name.lower())
                            destination = out_dir / name
                            crop.save(destination, "PNG")
                            self.log_line(f"Saved {destination}", level="OUTPUT")

                        total_pieces += len(rects)
                        bg_text = "#{:02X}{:02X}{:02X}".format(bg[0], bg[1], bg[2])
                        self.log_line(
                            f"{Path(src).name}: detected {len(rects)} image(s), background {bg_text}."
                        )

                except Exception as exc:
                    failures.append((src, str(exc)))
                    self.log_line(f"{Path(src).name}: {exc}", level="ERROR")

                self.progress["value"] = index
                self.update_idletasks()

            message = f"Finished. Exported {total_pieces} image(s) from {len(self.files)} sheet(s)."
            if failures:
                message += f"\n\n{len(failures)} file(s) had errors. See Results for details."
            self.log_line(message.replace("\n\n", " "))
            messagebox.showinfo(APP_NAME, message)

            if self.open_folder_var.get():
                self.open_path(output_root)

        finally:
            self.is_processing = False
            self.split_btn.configure(state="normal")
            self.update_install_button_state()

    def on_close(self):
        try:
            self.save_config(silent=True)
            if self.logging_enabled:
                self.write_log_file("Application closed.", "INFO")
        finally:
            self.destroy()


def main():
    configure_windows_process()
    App(parse_runtime_args()).mainloop()


if __name__ == "__main__":
    main()
