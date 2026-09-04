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

`load_rgi_layers.py` adds four groups under `<target>`, top to bottom:

  | Group                                | Color ramp                                                   | Hillshade below it            |
  | ------------------------------------ | ------------------------------------------------------------ | ----------------------------- |
  | `dh 2000-2020 (Hugonnet)`            | `<target>_dh`, `colormap_dh.txt`                             | `<target>_surface_clipped_hs` |
  | `Ice Thickness (Maffezzoli)`         | `<target>_thickness`, `colormap_thickness.txt`, 0 masked out | `<target>_surface_clipped_hs` |
  | `Surface DEM (COP)`                  | `<target>_surface`, `colormap_dem_topo.txt`                  | `<target>_surface_hs`         |
  | `Subglacial Topography (Maffezzoli)` | `<target>_bed`, `colormap_dem_bath_topo.txt`                 | `<target>_bed_hs`             |

Each group is a self-contained pair: the color ramp is multiplied onto its own hillshade,
so the shading shows through the colors. The groups stack with the derived quantities on
top of the geometry they came from; uncheck one to reveal the one below it.

The two DEM ramps differ only at the bottom end: `colormap_dem_bath_topo.txt` starts at
-2000 m so the bed's bathymetry gets its own blue, while `colormap_dem_topo.txt` starts at
0 m, since the ice surface never goes below sea level.

To add or drop a group or a layer, edit the `GROUPS` list at the top of
`load_rgi_layers.py`. Other variables in the same directory are `ftt_mask`,
`land_ice_area_fraction_retreat` and `tillwat`.

## Print layouts

`modeling-planning-AK.qgz` carries one print layout, **RGI C-01-03383**, framing that
glacier complex with a legend for the USGS mean rates, `dh` and the surface DEM. Its
legend is a customized one, so it refers to the raster layers by id; `load_rgi_layers.py`
gives them stable ids and re-points the legend at them, which means the layout only fills
in once you have clicked the Snow4Flow icon.

## Steps

To reduce the initial load time of the project, the raster layers are not automatically added
to the project. To load them, click on the Snow4Flow icon (the location on your toolbar may
vary). Depending on the network connection, it may take a moment to open the layers from AWS
West-2 (cloud optimized geotiffs); QGIS then streams only the overview levels it needs.

  1. Load a project.
  2. Click on the Snow4Flow icon (the location on your toolbar may vary).
  3. Save your project under a different name to avoid over-writing the version-controlled project. Unless it is your intend to make changes.
  4. If you accidentally save the version-controlled project, do `git checkout --  modeling-planning-region.qgz` where `region` is the project region that was over-written.
