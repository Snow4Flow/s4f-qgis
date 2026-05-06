"""
Add layers.
"""
# pylint: disable=import-outside-toplevel
import os
from pathlib import Path

from qgis.core import (
    QgsBilinearRasterResampler,
    QgsColorRampShader,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsHillshadeRenderer,
    QgsProject,
    QgsRasterLayer,
    QgsRasterRange,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsStyle,
)
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtWidgets import QApplication

# For a public bucket; for a private bucket, configure AWS creds instead.
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("AWS_REGION", "us-west-2")  # pism-cloud-data lives here
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

variables = [ "surface_clipped", "thickness", "bed"]
bucket = "pism-cloud-data"
prefix = "s4f/planning"
project = QgsProject.instance()
root = project.layerTreeRoot()

def _get_ramp(name: str, fallback: str = "Spectral"):
    """Return a color ramp by name from the default style, or a fallback if missing."""
    ramp = QgsStyle.defaultStyle().colorRamp(name)
    if ramp is None:
        print(f"Color ramp '{name}' not found; falling back to '{fallback}'")
        ramp = QgsStyle.defaultStyle().colorRamp(fallback)
    if ramp is None:
        raise RuntimeError(f"Neither '{name}' nor '{fallback}' color ramps are available")
    return ramp


def _load_qgis_colormap(path):
    """Parse a QGIS-exported color map ``.txt`` file (e.g. ``colormap_dem.txt``).

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


def add_layers():

    # Custom DEM color map for the bed layer (built fresh per layer below).
    dem_colormap_path = Path(__file__).parent / "colormap_dem.txt"
    dem_stops, dem_interp = _load_qgis_colormap(dem_colormap_path)

    thickness_colormap_path = Path(__file__).parent / "colormap_thickness.txt"
    thickness_stops, thickness_interp = _load_qgis_colormap(thickness_colormap_path)
    
    rgi_ids = [
        # "RGI2000-v7.0-C-07-00364",
        # "RGI2000-v7.0-C-07-00387",
        # "RGI2000-v7.0-C-07-00405",
        # "RGI2000-v7.0-C-07-00410",
        # "RGI2000-v7.0-C-07-00774",
        # "RGI2000-v7.0-C-07-00842",
        # "RGI2000-v7.0-C-07-00848",
        # "RGI2000-v7.0-C-03-00028",
        # "RGI2000-v7.0-C-03-00146",
        # "RGI2000-v7.0-C-03-00228",
        # "RGI2000-v7.0-C-03-00608",
        # "RGI2000-v7.0-C-03-00647",
        # "RGI2000-v7.0-C-03-00858",
        # "RGI2000-v7.0-C-03-01019",
        # "RGI2000-v7.0-C-03-01069",
        # "RGI2000-v7.0-C-03-01107",
        # "RGI2000-v7.0-C-03-01124",
        # "RGI2000-v7.0-C-03-01153",
        # "RGI2000-v7.0-C-03-01180",
        # "RGI2000-v7.0-C-03-01236",
        # "RGI2000-v7.0-C-03-01263",
        # "RGI2000-v7.0-C-03-01936",
        # "RGI2000-v7.0-C-03-02231",
        # "RGI2000-v7.0-C-03-02314",
        # "RGI2000-v7.0-C-03-02361",
        # "RGI2000-v7.0-C-03-02392",
        # "RGI2000-v7.0-C-03-02395",
        "RGI2000-v7.0-C-01-01407",
        "RGI2000-v7.0-C-01-03383",
        "RGI2000-v7.0-C-01-04374",
        "RGI2000-v7.0-C-01-05334",
        "RGI2000-v7.0-C-01-05881",
        "RGI2000-v7.0-C-01-06260",
        "RGI2000-v7.0-C-01-07967",
        "RGI2000-v7.0-C-01-08012",
        "RGI2000-v7.0-C-01-08153",
        "RGI2000-v7.0-C-01-08314",
        "RGI2000-v7.0-C-01-08321",
        "RGI2000-v7.0-C-01-08332",
        "RGI2000-v7.0-C-01-09429",
        "RGI2000-v7.0-C-01-11818",
        "RGI2000-v7.0-C-01-12784",
        "RGI2000-v7.0-C-01-14209",
        "RGI2000-v7.0-C-01-14612",
    ]

    top_group = root.findGroup("Glaciers") or root.addGroup("Glaciers")
    for i, rgi_id in enumerate(rgi_ids):
        group = top_group.findGroup(rgi_id) or top_group.addGroup(rgi_id)

        v = "thickness"

        name = f"{rgi_id}_{v}"
        layer_name = name
        uri = f"/vsis3/{bucket}/{prefix}/{rgi_id}/input/{name}.tif"
        
        if any(child.name() == layer_name for child in group.findLayers()):
            continue
        
        layer = QgsRasterLayer(uri, layer_name)
        if not layer.isValid():
            print(f"FAIL: {uri}")
            continue


        items = [
            QgsColorRampShader.ColorRampItem(value, QColor(r, g, b, a), label)
            for value, r, g, b, a, label in thickness_stops
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

        color_ramp_shader = QgsColorRampShader(vmin, vmax, source_ramp, thickness_interp)
        color_ramp_shader.setColorRampItemList(items)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(color_ramp_shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        renderer.setClassificationMin(vmin)
        renderer.setClassificationMax(vmax)
        layer.setRenderer(renderer)

        provider = layer.dataProvider()
        provider.setUserNoDataValue(1, [QgsRasterRange(0, 0)])  # band 1, treat 0 as NoData
        provider.setUseSourceNoDataValue(1, True)
        
        _apply_bilinear(layer)
        layer.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)

        layer.triggerRepaint()
        project.addMapLayer(layer, addToLegend=False)
        group.addLayer(layer)

        v = "surface_clipped"
        
        name = f"{rgi_id}_{v}"
        layer_name = f"{name}_hs"
        uri = f"/vsis3/{bucket}/{prefix}/{rgi_id}/input/{name}.tif"
        
        if any(child.name() == layer_name for child in group.findLayers()):
            continue
        
        layer = QgsRasterLayer(uri, layer_name)
        if not layer.isValid():
            print(f"FAIL: {uri}")
            continue
        
        renderer = QgsHillshadeRenderer(
            layer.dataProvider(),
            1,  # band number
            315.0,  # light azimuth (degrees, 0=N, clockwise)
            45.0,  # light altitude (degrees above horizon)
        )
        renderer.setMultiDirectional(True)
        renderer.setZFactor(2.0)  # bump if your terrain looks too flat
        layer.setRenderer(renderer)
        _apply_bilinear(layer)
        layer.triggerRepaint()
        project.addMapLayer(layer, addToLegend=False)
        group.addLayer(layer)

        v = "bed"

        name = f"{rgi_id}_{v}"
        layer_name = name
        uri = f"/vsis3/{bucket}/{prefix}/{rgi_id}/input/{name}.tif"
        
        if any(child.name() == layer_name for child in group.findLayers()):
            continue
        
        layer = QgsRasterLayer(uri, layer_name)
        if not layer.isValid():
            print(f"FAIL: {uri}")
            continue

        items = [
            QgsColorRampShader.ColorRampItem(value, QColor(r, g, b, a), label)
            for value, r, g, b, a, label in dem_stops
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

        color_ramp_shader = QgsColorRampShader(vmin, vmax, source_ramp, dem_interp)
        color_ramp_shader.setColorRampItemList(items)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(color_ramp_shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        renderer.setClassificationMin(vmin)
        renderer.setClassificationMax(vmax)
        layer.setRenderer(renderer)
        _apply_bilinear(layer)
        layer.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
        layer.triggerRepaint()
        project.addMapLayer(layer, addToLegend=False)
        group.addLayer(layer)


        v = "bed"
        
        name = f"{rgi_id}_{v}"
        layer_name = f"{name}_hs"
        uri = f"/vsis3/{bucket}/{prefix}/{rgi_id}/input/{name}.tif"
        
        if any(child.name() == layer_name for child in group.findLayers()):
            continue
        
        layer = QgsRasterLayer(uri, layer_name)
        if not layer.isValid():
            print(f"FAIL: {uri}")
            continue
        
        renderer = QgsHillshadeRenderer(
            layer.dataProvider(),
            1,  # band number
            315.0,  # light azimuth (degrees, 0=N, clockwise)
            45.0,  # light altitude (degrees above horizon)
        )
        renderer.setMultiDirectional(True)
        renderer.setZFactor(2.0)  # bump if your terrain looks too flat
        layer.setRenderer(renderer)
        
        # provider = layer.dataProvider()
        # provider.setUserNoDataValue(1, [QgsRasterRange(0, 0)])  # band 1, treat 0 as NoData
        # provider.setUseSourceNoDataValue(1, True)

        _apply_bilinear(layer)
        layer.triggerRepaint()
        project.addMapLayer(layer, addToLegend=False)
        group.addLayer(layer)
        
        # for v in variables:
        #     uri = f"/vsis3/{bucket}/{prefix}/{rgi_id}/input/{rgi_id}_{v}.tif"
        #     layer = QgsRasterLayer(uri, f"{rgi_id}_{v}")
        #     if not layer.isValid():
        #         print(f"FAIL: {uri}")
        #         continue

        #     if v in ("surface_clipped"):
        #         hs = QgsRasterLayer(uri, f"{rgi_id}_{v}_hs")
        #         if not hs.isValid():
        #             print(f"FAIL: {uri}")
        #             continue
        #         renderer = QgsHillshadeRenderer(
        #             hs.dataProvider(),
        #             1,  # band number
        #             315.0,  # light azimuth (degrees, 0=N, clockwise)
        #             45.0,  # light altitude (degrees above horizon)
        #         )
        #         renderer.setMultiDirectional(True)
        #         renderer.setZFactor(2.0)  # bump if your terrain looks too flat
        #         hs.setRenderer(renderer)
        #         hs.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
        #         _apply_bilinear(hs)
        #         hs.triggerRepaint()
        #         project.addMapLayer(hs, addToLegend=False)
        #         group.addLayer(hs)

        #     if v in ("bed"):
        #         hs = QgsRasterLayer(uri, f"{rgi_id}_{v}_hs")
        #         if not hs.isValid():
        #             print(f"FAIL: {uri}")
        #             continue
        #         renderer = QgsHillshadeRenderer(
        #             hs.dataProvider(),
        #             1,  # band number
        #             315.0,  # light azimuth (degrees, 0=N, clockwise)
        #             45.0,  # light altitude (degrees above horizon)
        #         )
        #         renderer.setMultiDirectional(True)
        #         renderer.setZFactor(2.0)  # bump if your terrain looks too flat
        #         hs.setRenderer(renderer)
        #         hs.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
        #         _apply_bilinear(hs)
        #         hs.triggerRepaint()
        #         project.addMapLayer(hs, addToLegend=False)
        #         group.addLayer(hs)

        #         vmin = -2000
        #         vmax = 2000
        #         ramp = oleron_src.clone()
        #         color_ramp_shader = QgsColorRampShader(vmin, vmax, ramp, QgsColorRampShader.Interpolated)
        #         color_ramp_shader.classifyColorRamp(classes=10)  # 10 stops; tune as desired
        #         shader = QgsRasterShader()
        #         shader.setRasterShaderFunction(color_ramp_shader)
        #         renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        #         layer.setRenderer(renderer)

        #         rf = layer.resampleFilter()
        #         rf.setZoomedInResampler(QgsBilinearRasterResampler())
        #         rf.setZoomedOutResampler(QgsBilinearRasterResampler())


        #         Layer.triggerRepaint()
        #         project.addMapLayer(layer, addToLegend=False)
        #         group.addLayer(layer)

        #     else:
        #         vmin = 0
        #         vmax = 1250
        #         ramp = lapaz_src.clone()
        #         color_ramp_shader = QgsColorRampShader(vmin, vmax, ramp, QgsColorRampShader.Interpolated)
        #         color_ramp_shader.classifyColorRamp(classes=10)  # 10 stops; tune as desired
        #         shader = QgsRasterShader()
        #         shader.setRasterShaderFunction(color_ramp_shader)

        #         renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        #         layer.setRenderer(renderer)
        #         _apply_bilinear(layer)

        #         provider = layer.dataProvider()
        #         provider.setUserNoDataValue(1, [QgsRasterRange(0, 0)])  # band 1, treat 0 as NoData
        #         provider.setUseSourceNoDataValue(1, True)

        #         layer.triggerRepaint()
        #         project.addMapLayer(layer, addToLegend=False)
        #         group.addLayer(layer)

        if i % 5 == 0:
            QApplication.processEvents()


if __name__ == "__main__":
    add_layers()
