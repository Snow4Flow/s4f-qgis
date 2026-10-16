"""
Project macros: the Snow4Flow toolbar button and what it does.

Loaded by the `openProject()` macro of each `modeling-planning-*.qgz`. The
button opens a small dialog with three choices:

  - Load from S3        stream the region's GeoTIFFs over /vsicurl/
  - Download from S3... pick a folder, fetch the GeoTIFFs into it, then load
                        them from there
  - Load from local...  pick a folder with an earlier download and load the
                        GeoTIFFs from there, no network involved

A download keeps a manifest (`s4f_manifest.json`) of what S3 reported for
each file, so the next download only fetches what changed on S3 or is
missing locally. "Re-download everything" overrides that.

Everything is read over plain HTTPS from the public bucket, no credentials.
"""
import importlib.util
import json
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path

from qgis.core import QgsApplication, QgsProject, QgsSettings, QgsTask
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from qgis.utils import iface

proj_dir = Path(QgsProject.instance().fileName()).parent
script = proj_dir / "load_rgi_layers.py"

MANIFEST = "s4f_manifest.json"
SETTINGS_KEY = "s4f/download_dir"
CHUNK = 1 << 20  # 1 MiB
TIMEOUT = 60  # seconds per HTTP request

REGION_NAMES = {"AK": "Alaska", "CA": "Arctic Canada", "SV": "Svalbard"}

_task = None  # keep the running download alive (the task manager holds a weak ref)


def _load_module():
    """Import load_rgi_layers.py fresh, so edits to it are picked up."""
    spec = importlib.util.spec_from_file_location("load_rgi_layers", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["load_rgi_layers"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fmt_size(nbytes):
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} B"
        nbytes /= 1024
    return f"{nbytes:.1f} GB"


# --------------------------------------------------------------------------
# Download bookkeeping (no QGIS GUI involved, so it can be tested headless)
# --------------------------------------------------------------------------

def read_manifest(folder):
    path = Path(folder) / MANIFEST
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            pass
    return {}


def write_manifest(folder, manifest):
    (Path(folder) / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True))


def remote_info(url):
    """What S3 says about `url`: size, ETag and Last-Modified, from a HEAD.

    Returns None when the object is not there (404). S3's ETag is not an
    MD5 for multipart uploads but it is stable per upload, which is all the
    comparison needs.
    """
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            headers = resp.headers
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return {
        "size": int(headers.get("Content-Length", 0)),
        "etag": headers.get("ETag", ""),
        "last_modified": headers.get("Last-Modified", ""),
    }


def local_status(mod, target, folder):
    """Split the region's files into those present in `folder` and the rest."""
    present, missing = [], []
    for filename in mod.region_files(target):
        (present if (Path(folder) / filename).is_file() else missing).append(filename)
    return present, missing


def plan_download(mod, target, folder, force=False):
    """Decide what to fetch: `[(filename, url, info, reason), ...]`.

    `reason` is "missing", "changed" or "forced"; files that are on S3,
    present locally with the size S3 reports, and whose manifest entry
    matches S3 are left out. Files that are not on S3 at all are skipped
    (the loader skips their group too). Also returns the skipped names and
    the up-to-date ones, for the confirmation message.
    """
    manifest = read_manifest(folder)
    todo, current, absent = [], [], []
    for filename in mod.region_files(target):
        url = mod.remote_url(target, filename)
        info = remote_info(url)
        if info is None:
            absent.append(filename)
            continue
        local = Path(folder) / filename
        known = manifest.get(filename)
        if force:
            reason = "forced"
        elif not local.exists() or local.stat().st_size != info["size"]:
            reason = "missing"
        elif known != info:
            reason = "changed"
        else:
            current.append(filename)
            continue
        todo.append((filename, url, info, reason))
    return todo, current, absent


def download_file(url, dest, progress=None, cancelled=None):
    """Stream `url` to `dest` via `dest.part`, renamed only once complete.

    `progress(nbytes)` is called per chunk with the bytes just written;
    `cancelled()` is polled per chunk and aborts (returning False) when
    true. Either way a half file never ends up under the final name.
    """
    part = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp, open(part, "wb") as out:
            while True:
                if cancelled is not None and cancelled():
                    return False
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                if progress is not None:
                    progress(len(chunk))
        part.replace(dest)
        return True
    finally:
        if part.exists():
            part.unlink()


class DownloadTask(QgsTask):
    """Fetch the planned files in the background, then load from the folder."""

    def __init__(self, plan, folder, on_done):
        super().__init__("Snow4Flow download", QgsTask.Flag.CanCancel)
        self.plan = plan
        self.folder = Path(folder)
        self.on_done = on_done
        self.total = sum(info["size"] for _, _, info, _ in plan) or 1
        self.done_bytes = 0
        self.fetched = []
        self.error = None

    def _progress(self, n):
        self.done_bytes += n
        self.setProgress(100.0 * self.done_bytes / self.total)

    def run(self):
        manifest = read_manifest(self.folder)
        try:
            for filename, url, info, _ in self.plan:
                ok = download_file(url, self.folder / filename,
                                   progress=self._progress, cancelled=self.isCanceled)
                if not ok:
                    return False
                manifest[filename] = info
                write_manifest(self.folder, manifest)  # per file: a cancel keeps what landed
                self.fetched.append(filename)
        except Exception as exc:  # pylint: disable=broad-except
            self.error = f"{type(exc).__name__}: {exc}"
            return False
        return True

    def finished(self, result):
        self.on_done(self, result)


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

class S4FDialog(QDialog):
    """Load from S3, or download to a folder first."""

    LOAD, DOWNLOAD, LOCAL = 1, 2, 3

    def __init__(self, region, target, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snow4Flow")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"<b>{REGION_NAMES.get(region, region)}</b> &nbsp; ({target})<br>"
            "Stream the planning rasters from S3, download them first,<br>"
            "or load a folder you downloaded them to earlier."))
        self.force = QCheckBox("Re-download everything, even files that are up to date")
        layout.addWidget(self.force)

        buttons = QHBoxLayout()
        load = QPushButton("Load from S3")
        download = QPushButton("Download from S3…")
        local = QPushButton("Load from local…")
        cancel = QPushButton("Cancel")
        load.setDefault(True)
        for b in (load, download, local, cancel):
            buttons.addWidget(b)
        layout.addLayout(buttons)

        load.clicked.connect(lambda: self.done(self.LOAD))
        download.clicked.connect(lambda: self.done(self.DOWNLOAD))
        local.clicked.connect(lambda: self.done(self.LOCAL))
        cancel.clicked.connect(self.reject)
        # the checkbox only means something for a download
        self.force.toggled.connect(lambda on: (load.setEnabled(not on), local.setEnabled(not on)))


def _report(kind, text):
    getattr(iface.messageBar(), kind)("Snow4Flow", text)


def _load(mod, local_dir=None):
    mod.add_layers(local_dir)
    where = f"from {local_dir}" if local_dir else "from S3"
    _report("pushSuccess", f"Layers loaded {where}")


def _pick_folder(title):
    """Native folder picker, starting at (and remembering) the last folder used."""
    settings = QgsSettings()
    folder = QFileDialog.getExistingDirectory(
        iface.mainWindow(), title,
        settings.value(SETTINGS_KEY, str(Path.home())),
        QFileDialog.Option.ShowDirsOnly)
    if folder:
        settings.setValue(SETTINGS_KEY, folder)
    return folder


def _load_local(mod, target):
    """Folder picker -> load whatever of the region's files is in there."""
    folder = _pick_folder("Choose the folder with the downloaded Snow4Flow data")
    if not folder:
        return
    present, missing = local_status(mod, target, folder)
    if not present:
        QMessageBox.warning(
            iface.mainWindow(), "Snow4Flow",
            f"No {target} GeoTIFFs in<br><tt>{folder}</tt>.<br>"
            "Use <i>Download from S3…</i> to fetch them first.")
        return
    _load(mod, folder)
    if missing:
        _report("pushWarning",
                f"{len(missing)} of {len(present) + len(missing)} files not in {folder}, "
                f"their groups were skipped: {', '.join(missing)}")


def _download(mod, target, force):
    """Folder picker -> plan -> confirm -> background download -> load."""
    global _task  # pylint: disable=global-statement
    folder = _pick_folder("Choose a folder for the Snow4Flow data")
    if not folder:
        return

    QgsApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        todo, current, absent = plan_download(mod, target, folder, force)
    finally:
        QgsApplication.restoreOverrideCursor()

    note = f"<br>Not on S3 for this region, skipped: {', '.join(absent)}" if absent else ""
    if not todo:
        QMessageBox.information(
            iface.mainWindow(), "Snow4Flow",
            f"All {len(current)} files in<br><tt>{folder}</tt><br>are up to date; "
            f"loading them from there.{note}")
        _load(mod, folder)
        return

    size = sum(info["size"] for _, _, info, _ in todo)
    lines = "".join(f"<li>{name} ({_fmt_size(info['size'])}, {reason})</li>"
                    for name, _, info, reason in todo)
    answer = QMessageBox.question(
        iface.mainWindow(), "Snow4Flow",
        f"Download {len(todo)} of {len(todo) + len(current)} files "
        f"({_fmt_size(size)}) to<br><tt>{folder}</tt>?<ul>{lines}</ul>"
        f"{len(current)} already up to date.{note}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes)
    if answer != QMessageBox.StandardButton.Yes:
        return

    def on_done(task, ok):
        global _task  # pylint: disable=global-statement
        _task = None
        if ok:
            try:
                _load(mod, folder)
            except Exception as exc:  # pylint: disable=broad-except
                _report("pushCritical", f"{type(exc).__name__}: {exc}")
                print(traceback.format_exc())
        elif task.error:
            _report("pushCritical", f"Download failed: {task.error} "
                                    f"({len(task.fetched)} files kept)")
        else:
            _report("pushWarning", f"Download cancelled, {len(task.fetched)} files kept")

    _task = DownloadTask(todo, folder, on_done)
    QgsApplication.taskManager().addTask(_task)
    _report("pushInfo", f"Downloading {_fmt_size(size)} to {folder}, see the progress bar")


def _run():
    try:
        mod = _load_module()
        region = mod._detect_region()  # pylint: disable=protected-access
        target = mod.REGIONS[region]["target"]
        dialog = S4FDialog(region, target, iface.mainWindow())
        choice = dialog.exec()
        if choice == S4FDialog.LOAD:
            _load(mod)
        elif choice == S4FDialog.DOWNLOAD:
            _download(mod, target, dialog.force.isChecked())
        elif choice == S4FDialog.LOCAL:
            _load_local(mod, target)
    except Exception as exc:  # pylint: disable=broad-except
        _report("pushCritical", f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())


def _remove_rgi_action():
    """Remove any previously-installed Snow4Flow button."""
    for action in iface.mainWindow().findChildren(QAction):
        if action.objectName() == "rgi_load_action":
            iface.removeToolBarIcon(action)
            action.deleteLater()


def install_toolbar_button():
    """Install the Snow4Flow toolbar button. Called from the QGIS project
    macro's `openProject()`."""
    _remove_rgi_action()  # purge any pre-existing copies first
    action = QAction(
        QIcon(str(proj_dir / "images" / "S4F_logo_darkbg_notext.png")),
        "Snow4Flow layers",
        iface.mainWindow(),
    )
    action.setObjectName("rgi_load_action")  # stable id for cleanup
    action.setToolTip("Load the Snow4Flow planning rasters from S3, from a download, "
                      "or download them first")
    action.triggered.connect(_run)
    iface.addToolBarIcon(action)


def uninstall_toolbar_button():
    """Remove the toolbar button. Called from the QGIS project macro's
    `closeProject()`."""
    _remove_rgi_action()
