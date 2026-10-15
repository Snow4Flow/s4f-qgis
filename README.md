# s4f-qgis

## modeling-planning

For each of the three Snow4Flow regions we have a corresponding QGIS4 project.

  | Project                     | Domain            | Region         | Project CRS |
  | --------------------------- | ----------------- | -------------- | ----------- |
  | `modeling-planning-AK.qgz`  | `S4F_target_01`   | Alaska         | EPSG:5936   |
  | `modeling-planning-CA.qgz`  | `S4F_target_03`   | Arctic Canada  | EPSG:3413   |
  | `modeling-planning-SV.qgz`  | `S4F_target_07`   | Svalbard       | EPSG:3413   |

Each project CRS is the native CRS of that domain's GeoTIFFs, so nothing is reprojected on the fly.

## Data

Everything is read straight from the public `pism-cloud-data` bucket in AWS `us-west-2`;
nothing needs to be downloaded and no AWS credentials are required. The layers use GDAL's
`/vsicurl/` over plain HTTPS rather than `/vsis3/`, which would need credentials (or
`AWS_NO_SIGN_REQUEST`) set in the environment before QGIS starts.

  - `.../s4f/planning/s4f_c.fgb` — RGI glacier complexes (all regions), loaded with the
    project as *RGI Glacier Complexes*.
  - `.../s4f/planning/<target>/input/<target>_<variable>.tif` — one cloud-optimized
    GeoTIFF per variable covering the whole domain.

where `...` is `https://pism-cloud-data.s3.us-west-2.amazonaws.com`.

`load_rgi_layers.py` adds up to six groups under `<target>`, top to bottom:

  | Group                                | Color ramp                                                              | Hillshade below it                                          |
  | ------------------------------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------- |
  | `ITS_LIVE`                           | *v*: `<target>_its_live_v`, `colormap_speed.txt`                        | *Hillshade (glacier only)*: `<target>_surface_clipped_hs`   |
  | `dh 2000-2020 (Hugonnet)`            | *dh*: `<target>_dh`, `colormap_dh.txt`                                  | *Hillshade (glacier only)*: `<target>_surface_clipped_hs`   |
  | `CARRA2 Snowfall 1990-2019`          | *Snowfall*: `<target>_carra2_snowfall_1990_2019`, `colormap_snowfall.txt` | *Hillshade*: `<target>_surface_hs_carra2`                 |
  | `Ice Thickness (Maffezzoli)`         | *Thickness*: `<target>_thickness`, `colormap_thickness.txt`, 0 masked out | *Hillshade (glacier only)*: `<target>_surface_clipped_hs` |
  | `Surface DEM (COP)`                  | *Surface*: `<target>_surface`, `colormap_dem_topo.txt`                  | *Hillshade*: `<target>_surface_hs`                          |
  | `Subglacial Topography (Maffezzoli)` | *Bed*: `<target>_bed`, `colormap_dem_bath_topo.txt`                     | *Hillshade (subglacial topography)*: `<target>_bed_hs`      |

The italic names are what the layer tree shows; the `<target>_...` names are the layer
ids (and the GeoTIFF basenames on S3), which stay fixed so print layouts can refer to them.

Each group is a self-contained pair: the color ramp is multiplied onto its own hillshade,
so the shading shows through the colors. The groups stack with the derived quantities on
top of the geometry they came from; uncheck one to reveal the one below it.

The two DEM ramps differ only at the bottom end: `colormap_dem_bath_topo.txt` starts at
-2000 m so the bed's bathymetry gets its own blue, while `colormap_dem_topo.txt` starts at
0 m, since the ice surface never goes below sea level.

`colormap_speed.txt` is the ITS_LIVE surface-speed ramp, 10 to 750 m/yr; speeds below 10
get the lowest color rather than being masked. `colormap_snowfall.txt` is the CARRA2 ramp,
0 to 10.

A group is only added where its color-ramp GeoTIFF exists on S3; the script says so in
the Python console when it skips one. `CARRA2 Snowfall 1990-2019` is the only group that
is not available for every domain yet.

To add or drop a group or a layer, edit the `GROUPS` list at the top of
`load_rgi_layers.py`. Other variables in the same directory are `ftt_mask`,
`land_ice_area_fraction_retreat` and `tillwat`.

## Basemap

Each project has *ESRI World Imagery* as an XYZ tile layer at the bottom of the layer tree,
checked on open. It is served in web mercator and QGIS warps the tiles into the project CRS
on the fly; at the latitudes of the three domains that looks fine. The loader puts the
`<target>` group right above it.

## Map decorations

All three projects carry a north arrow (upper right, follows true north for the polar
stereographic project CRS as you pan) and a scale bar (lower left, snapped to round numbers)
as canvas decorations. Adjust them under *View ▸ Decorations*; they are saved with the
project.

## Print layouts

`modeling-planning-AK.qgz` carries one print layout, **RGI C-01-03383**, framing that
glacier complex with a legend for the USGS mean rates, `dh` and the surface DEM. Its
legend is a customized one, so it refers to the raster layers by id; `load_rgi_layers.py`
gives them stable ids and re-points the legend at them, which means the layout only fills
in once you have clicked the Snow4Flow icon.

## Steps

To reduce the initial load time of the project, the raster layers are not automatically added
to the project. The Snow4Flow icon (the location on your toolbar may vary) opens a dialog with
two choices:

  - **Load from S3** streams the cloud-optimized GeoTIFFs from AWS us-west-2. Depending on
    the network connection it may take a moment to open the layers; QGIS then streams only
    the overview levels it needs.
  - **Download from S3…** asks for a folder, downloads the region's GeoTIFFs into it (a
    progress bar appears in the message bar, and the download can be cancelled) and then
    loads the layers from there. The sizes are roughly 4 GB for Alaska, 0.7 GB for Arctic
    Canada and 0.3 GB for Svalbard. The folder is remembered for next time.

A download keeps a small `s4f_manifest.json` next to the files with what S3 reported for
each of them (size, ETag, Last-Modified). Choosing *Download from S3…* again only fetches
files that changed on S3 since, or that are missing locally, so it doubles as "load the
local copy". Tick *Re-download everything* to fetch all of them regardless. Files are
written as `.part` and renamed once complete, so an interrupted download never leaves a
truncated GeoTIFF behind under its final name.

Layers that are already in the project are not added twice: switching between S3 and a
download, or to a fresh download, just re-points them at the new source and keeps their
styling and the print layout intact.

The RGI glacier complexes and the USGS benchmark layers are still read from S3 by the
projects themselves; the download covers the rasters only.

  1. Load a project.
  2. Click on the Snow4Flow icon and pick *Load from S3* or *Download from S3…*.
  3. Save your project under a different name to avoid over-writing the version-controlled project. Unless it is your intend to make changes.
  4. If you accidentally save the version-controlled project, do `git checkout --  modeling-planning-region.qgz` where `region` is the project region that was over-written.
