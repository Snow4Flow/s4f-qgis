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
    project as *S4F RGI Glacier Complexes*.
  - `.../s4f/planning/<target>/input/<target>_<variable>.tif` — one cloud-optimized
    GeoTIFF per variable covering the whole domain.

where `...` is `https://pism-cloud-data.s3.us-west-2.amazonaws.com`.

`load_rgi_layers.py` adds these rasters, top to bottom:

  1. `<target>_thickness` — ice thickness, `colormap_thickness.txt`, 0 masked out
  2. `<target>_surface_clipped_hs` — hillshaded ice surface
  3. `<target>_bed` — bed topography, `colormap_dem.txt`
  4. `<target>_bed_hs` — hillshaded bed topography

To add or drop a variable, edit the `LAYERS` list at the top of `load_rgi_layers.py`.
Other variables in the same directory are `surface`, `ftt_mask`,
`land_ice_area_fraction_retreat` and `tillwat`.

## Steps

To reduce the initial load time of the project, the raster layers are not automatically added
to the project. To load them, click on the Snow4Flow icon (the location on your toolbar may
vary). Depending on the network connection, it may take a moment to open the layers from AWS
West-2 (cloud optimized geotiffs); QGIS then streams only the overview levels it needs.

  1. Load a project.
  2. Click on the Snow4Flow icon (the location on your toolbar may vary).
  3. Save your project under a different name to avoid over-writing the version-controlled project. Unless it is your intend to make changes.
  4. If you accidentally save the version-controlled project, do `git checkout --  modeling-planning-region.qgz` where `region` is the project region that was over-written.
