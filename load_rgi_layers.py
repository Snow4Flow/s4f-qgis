"""
Add the Snow4Flow planning layers for a region to the current QGIS project.

Each region has one set of domain-wide cloud-optimized GeoTIFFs in the public
``pism-cloud-data`` bucket under ``s4f/planning/<target>/input/``, so there is
nothing to loop over: one ``QgsRasterLayer`` per variable covers the whole
domain and QGIS streams only the overview levels/tiles it needs.

``add_layers()`` streams them from S3; ``add_layers(local_dir)`` reads the
same files from a folder ``project_properties.py`` downloaded them to, and
re-points layers that are already in the project instead of adding twice.
"""
# pylint: disable=import-outside-toplevel
import os
import re
from pathlib import Path

from qgis.core import (
    QgsBilinearRasterResampler,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsDataProvider,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsHillshadeRenderer,
    QgsLayoutItemLegend,
    QgsProject,
    QgsRasterLayer,
    QgsRasterRange,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
)
from qgis.PyQt.QtGui import QColor, QPainter

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

# Read over plain HTTPS rather than /vsis3/, which would need AWS credentials
# (or AWS_NO_SIGN_REQUEST) in the environment before QGIS even starts. The
# bucket is public, so /vsicurl/ works for everyone with no setup at all.
BASE_URL = "https://pism-cloud-data.s3.us-west-2.amazonaws.com/s4f/planning"

project = QgsProject.instance()
root = project.layerTreeRoot()

# Per-region settings. Project filename suffix (`-AK`, `-CA`, `-SV`)
# selects which entry to use; see `_detect_region()`. `crs` is the CRS of
# that region's GeoTIFFs, so the project matches the data natively.
REGIONS = {
    "AK": {"target": "S4F_target_01", "crs": "EPSG:5936"},  # Alaska Polar Stereographic
    "CA": {"target": "S4F_target_03", "crs": "EPSG:3413"},  # NSIDC Sea Ice Polar Stereographic North
    "SV": {"target": "S4F_target_07", "crs": "EPSG:3413"},  # NSIDC Sea Ice Polar Stereographic North
}

# Layer groups to add, in drawing order: the first entry ends up on top, both
# for the groups and for the layers inside one.
#   name:   the sub-group as it appears in the layer tree
#   layers: what goes in it, each one
#     variable:  the `<target>_<variable>.tif` suffix on S3
#     label:     the name shown in the layer tree; the layer *id* stays
#                `<target>_<variable><suffix>` so print layouts can find it
#     style:     "hillshade", or the colormap `.txt` to build a pseudocolor ramp from
#     suffix:    appended to the layer id (to tell a hillshade apart from the ramp)
#     mask_zero: treat 0 as NoData (thickness has 0 outside the ice)
#     multiply:  composite onto what is below instead of painting over it
#
# Each group is a pair: a color ramp multiplied onto its own hillshade, so the
# shading shows through the colors and every group is self-contained. The
# groups stack with the derived quantities on top of the geometry they came
# from; uncheck one to reveal the one below.
#
# A group whose first layer is not on S3 for the region is dropped entirely:
# a hillshade on its own would just be clutter.
GLACIER_HILLSHADE = {"variable": "surface_clipped", "suffix": "_hs",
                     "label": "Hillshade (glacier only)", "style": "hillshade"}

GROUPS = [
    {
        "name": "ITS_LIVE",
        "layers": [
            {"variable": "its_live_v", "label": "v", "style": "colormap_speed.txt",
             "multiply": True},
            GLACIER_HILLSHADE,
        ],
    },
    {
        "name": "dh 2000-2020 (Hugonnet)",
        "layers": [
            {"variable": "dh", "label": "dh", "style": "colormap_dh.txt", "multiply": True},
            GLACIER_HILLSHADE,
        ],
    },
    {
        # CARRA2 is a regional reanalysis; the COG only exists where the
        # domain is covered (Alaska so far). Elsewhere the group is skipped.
        "name": "CARRA2 Snowfall 1990-2019",
        "layers": [
            {"variable": "carra2_snowfall_1990_2019", "label": "Snowfall",
             "style": "colormap_snowfall.txt", "multiply": True},
            {"variable": "surface", "suffix": "_hs_carra2", "label": "Hillshade",
             "style": "hillshade"},
        ],
    },
    {
        "name": "Ice Thickness (Maffezzoli)",
        "layers": [
            {"variable": "thickness", "label": "Thickness", "style": "colormap_thickness.txt",
             "mask_zero": True, "multiply": True},
            GLACIER_HILLSHADE,
        ],
    },
    {
        "name": "Surface DEM (COP)",
        "layers": [
            {"variable": "surface", "label": "Surface", "style": "colormap_dem_topo.txt",
             "multiply": True},
            {"variable": "surface", "suffix": "_hs", "label": "Hillshade", "style": "hillshade"},
        ],
    },
    {
        "name": "Subglacial Topography (Maffezzoli)",
        "layers": [
            {"variable": "bed", "label": "Bed", "style": "colormap_dem_bath_topo.txt",
             "multiply": True},
            {"variable": "bed", "suffix": "_hs", "label": "Hillshade (subglacial topography)",
             "style": "hillshade"},
        ],
    },
]


def _detect_region():
    """Return the region code (AK/CA/SV) from the QGIS project filename.

    Expected naming: `modeling-planning-{REGION}.qgz`. Falls back to AK
    with a printed warning so opening any other project doesn't blow up.
    """
    stem = Path(QgsProject.instance().fileName()).stem
    suffix = stem.rsplit("-", 1)[-1].upper()
    if suffix in REGIONS:
        return suffix
    print(f"load_rgi_layers: could not infer region from project name "
          f"'{stem}'; defaulting to AK")
    return "AK"


def region_files(target):
    """The GeoTIFF basenames `GROUPS` needs for `target`, in load order.

    `surface_clipped` and `surface` are shared by several groups, so this is
    shorter than the layer list. Each is `<target>_<variable>.tif` both on
    S3 (under `<target>/input/`) and in a download folder.
    """
    names = []
    for group_spec in GROUPS:
        for spec in group_spec["layers"]:
            name = f"{target}_{spec['variable']}.tif"
            if name not in names:
                names.append(name)
    return names


def remote_url(target, filename):
    """Plain HTTPS URL of one of the region's GeoTIFFs."""
    return f"{BASE_URL}/{target}/input/{filename}"


def _uri(target, filename, local_dir):
    """GDAL source for a GeoTIFF: a local path, or /vsicurl/ over S3."""
    if local_dir:
        return str(Path(local_dir) / filename)
    return f"/vsicurl/{remote_url(target, filename)}"


def _load_qgis_colormap(path):
    """Parse a QGIS-exported color map ``.txt`` file (e.g. ``colormap_dem_topo.txt``).

    The file format is::

        # comment
        INTERPOLATION:INTERPOLATED
        value, r, g, b, a, label

    Returns ``(stops, interpolation)`` where ``stops`` is a list of
    ``(value, r, g, b, a, label)`` tuples and ``interpolation`` is the
    matching ``QgsColorRampShader`` type.
    """
    interp = QgsColorRampShader.Interpolated
    stops = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("INTERPOLATION:"):
            kind = line.split(":", 1)[1].strip().upper()
            interp = {
                "INTERPOLATED": QgsColorRampShader.Interpolated,
                "DISCRETE": QgsColorRampShader.Discrete,
                "EXACT": QgsColorRampShader.Exact,
            }.get(kind, QgsColorRampShader.Interpolated)
            continue
        parts = [p.strip() for p in line.split(",")]
        value = float(parts[0])
        r, g, b = int(parts[1]), int(parts[2]), int(parts[3])
        a = int(parts[4]) if len(parts) > 4 else 255
        label = parts[5] if len(parts) > 5 else str(value)
        stops.append((value, r, g, b, a, label))
    return stops, interp


def _unique_id(base):
    """Return a stable layer id derived from `<target>_<variable><suffix>`.

    QGIS otherwise mints a random UUID per session, so anything that
    references a layer by id -- the print layouts, most of all -- would break
    the next time the layers are loaded. `surface_clipped_hs` appears in
    several groups, hence the counter.
    """
    layer_id, n = base, 2
    while project.mapLayer(layer_id) is not None:
        layer_id, n = f"{base}_{n}", n + 1
    return layer_id


def _group_layer(group, base):
    """The layer in `group` whose id came from `base`, or None."""
    pattern = re.compile(rf"^{re.escape(base)}(_\d+)?$")
    for child in group.findLayers():
        if pattern.match(child.layerId()):
            return child.layer()
    return None


def _apply_bilinear(layer):
    """Enable bilinear resampling on both zoom-in and zoom-out.

    Sets it on the data provider (the path COGs use) AND on the legacy
    resampleFilter, so it works regardless of which path QGIS picks.
    """
    provider = layer.dataProvider()
    provider.enableProviderResampling(True)
    provider.setZoomedInResamplingMethod(provider.ResamplingMethod.Bilinear)
    provider.setZoomedOutResamplingMethod(provider.ResamplingMethod.Bilinear)
    provider.setMaxOversampling(2.0)

    rf = layer.resampleFilter()
    if rf is not None:  # hillshade renderer doesn't expose one
        rf.setZoomedInResampler(QgsBilinearRasterResampler())
        rf.setZoomedOutResampler(QgsBilinearRasterResampler())


def _pseudocolor_renderer(layer, stops, interp):
    """Build a single-band pseudocolor renderer from parsed colormap stops."""
    items = [
        QgsColorRampShader.ColorRampItem(value, QColor(r, g, b, a), label)
        for value, r, g, b, a, label in stops
    ]
    vmin = items[0].value
    vmax = items[-1].value

    # Build a gradient ramp from the stops so the legend swatch renders
    # the full color ramp instead of a flat gray bar.
    intermediate_stops = [
        QgsGradientStop((it.value - vmin) / (vmax - vmin), it.color)
        for it in items[1:-1]
    ]
    source_ramp = QgsGradientColorRamp(
        items[0].color, items[-1].color, False, intermediate_stops
    )

    color_ramp_shader = QgsColorRampShader(vmin, vmax, source_ramp, interp)
    color_ramp_shader.setColorRampItemList(items)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(color_ramp_shader)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    renderer.setClassificationMin(vmin)
    renderer.setClassificationMax(vmax)
    return renderer


def _hillshade_renderer(layer):
    """Build a multidirectional hillshade renderer for a DEM band."""
    renderer = QgsHillshadeRenderer(
        layer.dataProvider(),
        1,  # band number
        315.0,  # light azimuth (degrees, 0=N, clockwise)
        45.0,  # light altitude (degrees above horizon)
    )
    renderer.setMultiDirectional(True)
    renderer.setZFactor(2.0)  # bump if your terrain looks too flat
    return renderer


def _refresh_layout_legends():
    """Point the saved print layouts' legends at the layers we just added.

    A layout legend with a customized model (ours renames the groups, so it
    has one) resolves its layer references when the project is read -- long
    before these layers exist. Without this the legend comes up with empty
    entries; the layer ids `_unique_id()` hands out are what it looks for.
    """
    for layout in project.layoutManager().layouts():
        for item in layout.items():
            if isinstance(item, QgsLayoutItemLegend):
                item.model().rootGroup().resolveReferences(project)
                item.updateLegend()


def _style_layer(layer, spec, colormaps):
    """Apply the renderer, blend mode, NoData and resampling `spec` asks for.

    Everything here is derived from `spec`, so it can be re-applied after
    the layer's data source changes (which recreates the data provider and
    with it the NoData and resampling settings).
    """
    if spec["style"] == "hillshade":
        layer.setRenderer(_hillshade_renderer(layer))
    else:
        path = Path(__file__).parent / spec["style"]
        if spec["style"] not in colormaps:
            colormaps[spec["style"]] = _load_qgis_colormap(path)
        layer.setRenderer(_pseudocolor_renderer(layer, *colormaps[spec["style"]]))

    if spec.get("multiply"):
        layer.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)

    if spec.get("mask_zero"):
        provider = layer.dataProvider()
        provider.setUserNoDataValue(1, [QgsRasterRange(0, 0)])  # band 1, treat 0 as NoData
        provider.setUseSourceNoDataValue(1, True)

    _apply_bilinear(layer)
    layer.triggerRepaint()


def add_layers(local_dir=None):
    """Add every layer in `GROUPS` for the project's region.

    With `local_dir`, the GeoTIFFs are read from that folder instead of S3.
    A layer that is already in the project is kept -- re-pointed at the new
    source if that differs, so switching between S3 and a download, or to a
    fresh download, never duplicates anything.
    """
    region = _detect_region()
    target = REGIONS[region]["target"]
    crs = REGIONS[region]["crs"]
    project.setCrs(QgsCoordinateReferenceSystem(crs))
    print(f"load_rgi_layers: region={region}, target={target}, crs={crs}, "
          f"source={local_dir or 'S3'}")

    colormaps = {}  # parsed once, reused across layers
    target_group = root.findGroup(target) or root.addGroup(target)

    for group_spec in GROUPS:
        # Collapsed by default: four two-layer groups expanded is a wall of
        # entries, and the group name already says what is in there.
        group = target_group.findGroup(group_spec["name"])
        if group is None:
            group = target_group.addGroup(group_spec["name"])
            group.setExpanded(False)

        for spec in group_spec["layers"]:
            variable = spec["variable"]
            filename = f"{target}_{variable}.tif"
            base_id = f"{target}_{variable}{spec.get('suffix', '')}"
            uri = _uri(target, filename, local_dir)

            layer = _group_layer(group, base_id)
            if layer is not None:
                if layer.source() != uri:
                    # Same layer, new source: the provider is rebuilt, so
                    # the style (NoData, resampling) has to be re-applied.
                    layer.setDataSource(uri, layer.name(), "gdal",
                                        QgsDataProvider.ProviderOptions())
                    if layer.isValid():
                        _style_layer(layer, spec, colormaps)
                    else:
                        print(f"FAIL: {uri}")
                continue

            layer = QgsRasterLayer(uri, spec.get("label", base_id))
            if not layer.isValid():
                print(f"FAIL: {uri}")
                if not group.findLayers():
                    print(f"load_rgi_layers: skipping group '{group_spec['name']}' "
                          f"for {target}, no {filename}")
                    target_group.removeChildNode(group)
                    break
                continue
            layer.setId(_unique_id(base_id))
            _style_layer(layer, spec, colormaps)
            project.addMapLayer(layer, addToLegend=False)
            group.addLayer(layer)

    _refresh_layout_legends()


if __name__ == "__main__":
    add_layers()
