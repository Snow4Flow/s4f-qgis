from qgis.utils import iface                                                                                                                     

import importlib.util, sys
from pathlib import Path
from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QAction
import importlib.util
import sys
import traceback
from pathlib import Path
from qgis.core import QgsProject
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


proj_dir = Path(QgsProject.instance().fileName()).parent
script = proj_dir / "load_rgi_layers.py"

def _remove_rgi_action():
    """Remove any previously-installed Load RGI Layers button."""
    main_window = iface.mainWindow()
    for action in main_window.findChildren(QAction):
        if action.objectName() == "rgi_load_action":
            iface.removeToolBarIcon(action)
            action.deleteLater()

def openProject():

    def _run():
        try:
            spec = importlib.util.spec_from_file_location("load_rgi_layers", script)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["load_rgi_layers"] = mod
            spec.loader.exec_module(mod)
            mod.add_layers()
            iface.messageBar().pushSuccess("load_rgi_layers", "Layers added")
        except Exception as exc:
            iface.messageBar().pushCritical("load_rgi_layers", f"{type(exc).__name__}: {exc}")                                             
            print(traceback.format_exc())                                                     

    # Always purge any pre-existing copies before installing a new one
    _remove_rgi_action()

    action = QAction(
        QIcon(":/images/themes/default/mActionAddLayer.svg"),
        "Load RGI layers",
        iface.mainWindow(),
    )

    action.setObjectName("rgi_load_action")     # stable id for cleanup
    action.setToolTip("Fetch and add the per-glacier raster layers from S3")
    action.triggered.connect(_run)
    iface.addToolBarIcon(action)

def saveProject():
    pass                                                  


def closeProject():
    _remove_rgi_action()
