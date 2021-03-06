# About

This project is a plugin for QGIS 2 that provides custom tools for digitizing:
- Extend
- Fillet
- Mirror
- Scale
- Trim
- Intersect
- Explode
- Move
- Copy
- Move multiple layers (selected)
- Copy multiple layers (selected)
- Parallel
- Split
- Centerline
- Draw arc
- Polygonize

# Install

## From Github

1. Download a ZIP of the repository or clone it using "git clone"
2. The folder with the Python files should be directly under the directory with all the QGIS plugins (for example, ~/.qgis2/python/plugins/GVDigitizingTools)
3. Compile the assets and UI: 
    - On Windows, launch the OSGeo4W Shell. On Unix, launch a command line and make sure the PyQT tools (pyuic4 and pyrcc4) are on the PATH
    - Go to the plugin directory
    - Launch "build.bat" or "build.sh"
4. The next time QGIS is opened, the plugin should be listed in the "Plugins" > "Manage and install plugin" dialog

# Documentation

Some documentation (not up-to-date) is on: https://gvellut.github.io/GVDigitizingTools/

# Limitations & TODO

- Old project (made for QGIS 2.2 in 2014)
- Some of the tools may now be provided by QGIS so no longer necessary
- Some workarounds for QGIS bugs may no longer be necessary
- Much cleanup still needs to be performed to remove quite specific assumptions about the .qgs project
- Cleanup for PEP-8
- Documentation needs to be updated
- Release on QGIS plugin registry


