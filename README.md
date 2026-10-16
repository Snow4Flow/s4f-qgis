# s4f-qgis

## modeling-planning

For each of the three Snow4Flow regions we have a corresponding QGIS4 project.

  - modeling-planning-AK.qgz
  - modeling-planning-CA.qgz
  - modeling-planning-SV.qgz 

## Steps

To reduce the initial load time of the project, the layers are not automatically added to the project. To load the layers, click on the Snow4Flow icon (the location on your toolbar may vary). Depending on the network connection, it may take 1-2 minutes to load the loaders from AWS West-2 (cloud optimized geotiffs).

  1. Load a project.
  2. Click on the Snow4Flow icon (the location on your toolbar may vary).
  3. Save your project under a different name to avoid over-writing the version-controlled project. Unless it is your intend to make changes.
  4. If you accidentally save the version-controlled project, do `git checkout --  modeling-planning-region.qgz` where `region` is the project region that was over-written.
