# -*- coding: utf-8 -*-
"""
create_dirt_mound.py

Run in the QGIS 3.x Python Console (or as a "Run Script" in the Script Editor).

WHAT IT DOES
------------
1. Reads the currently selected point feature from the active point layer.
2. Reads a DEM raster you choose from a list of loaded raster layers.
3. Asks you to supply TWO of the following three mound parameters (the
   third is calculated automatically from the standard cone relationship
   tan(angle_of_repose) = height / radius):
        - Angle of repose (degrees)
        - Height (map/vertical units, e.g. metres)
        - Diameter (map units, e.g. metres)
4. Builds a talus-profile mound centered on the selected point: concave
   in cross-section (steepest near the crest, flattening smoothly toward
   the toe, like a real scree/talus pile) rather than a straight-sided
   cone. The mound still hits exactly the requested height at the center
   and exactly zero at the requested radius/diameter -- only the shape of
   the curve in between changes. You can adjust how pronounced the
   concavity is (a "talus exponent"; 1.0 = straight-line cone, higher
   values = more concave/curved). It's added on top of the existing DEM
   elevations, and the result is written to a NEW raster file (the
   original DEM is left untouched).
5. Optionally loads the new DEM into the QGIS project.

USAGE
-----
Select exactly one point feature in a point layer (Identify/select tool),
make sure the DEM you want to modify is loaded in the project, then paste
this script into the QGIS Python Console (or Plugins > Python Console >
Show Editor > open this file > Run) and execute it.
"""

import os
import math
import numpy as np

from osgeo import gdal, osr
from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsWkbTypes,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsRasterLayer,
)
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox, QFileDialog
from qgis.utils import iface

gdal.UseExceptions()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _warn(msg):
    QMessageBox.warning(None, "Dirt Mound Tool", msg)


def _info(msg):
    QMessageBox.information(None, "Dirt Mound Tool", msg)


def pick_point_layer():
    """Return the active layer if it's a point vector layer with a selection,
    otherwise let the user pick one from the loaded point layers."""
    point_layers = [
        lyr for lyr in QgsProject.instance().mapLayers().values()
        if lyr.type() == QgsMapLayer.VectorLayer
        and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.PointGeometry
    ]
    if not point_layers:
        _warn("No point layers are loaded in this project.")
        return None

    active = iface.activeLayer()
    if (
        active in point_layers
        and active.selectedFeatureCount() > 0
    ):
        return active

    names = [lyr.name() for lyr in point_layers]
    name, ok = QInputDialog.getItem(
        None, "Select Point Layer",
        "Choose the point layer containing your mound-center point:",
        names, 0, False
    )
    if not ok:
        return None
    return next(lyr for lyr in point_layers if lyr.name() == name)


def pick_dem_layer():
    """Let the user pick a loaded raster layer to use as the source DEM."""
    raster_layers = [
        lyr for lyr in QgsProject.instance().mapLayers().values()
        if lyr.type() == QgsMapLayer.RasterLayer
    ]
    if not raster_layers:
        _warn("No raster layers are loaded in this project.")
        return None

    names = [lyr.name() for lyr in raster_layers]
    name, ok = QInputDialog.getItem(
        None, "Select DEM", "Choose the DEM raster layer:",
        names, 0, False
    )
    if not ok:
        return None
    return next(lyr for lyr in raster_layers if lyr.name() == name)


def get_selected_point_geom(point_layer):
    """Return the (x, y) of the single selected point feature, in the
    point layer's own CRS."""
    feats = list(point_layer.selectedFeatures())
    if len(feats) == 0:
        _warn("No feature is selected in layer '{}'.\n"
              "Select one point feature and re-run the script.".format(
                  point_layer.name()))
        return None
    if len(feats) > 1:
        _warn("More than one feature is selected. "
              "Please select exactly one point and re-run.")
        return None

    geom = feats[0].geometry()
    if geom.isMultipart():
        pt = geom.asMultiPoint()[0]
    else:
        pt = geom.asPoint()
    return pt.x(), pt.y()


def transform_point(x, y, src_crs, dst_crs):
    """Reproject (x, y) from src_crs to dst_crs if they differ."""
    if src_crs == dst_crs:
        return x, y
    xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
    pt = xform.transform(x, y)
    return pt.x(), pt.y()


def ask_two_of_three_params():
    """Ask the user which parameter to derive, then collect the other two.
    Returns (angle_deg, height, diameter) with the derived one filled in."""
    choices = [
        "Diameter  (derive from Angle of Repose + Height)",
        "Height    (derive from Angle of Repose + Diameter)",
        "Angle of Repose  (derive from Height + Diameter)",
    ]
    choice, ok = QInputDialog.getItem(
        None, "Mound Parameters",
        "Which parameter should be calculated automatically?",
        choices, 0, False
    )
    if not ok:
        return None

    angle_deg = height = diameter = None

    if choice.startswith("Diameter"):
        angle_deg, ok1 = QInputDialog.getDouble(
            None, "Angle of Repose", "Angle of repose (degrees, e.g. 34):",
            34.0, 0.1, 89.9, 2)
        if not ok1:
            return None
        height, ok2 = QInputDialog.getDouble(
            None, "Height", "Mound height (map vertical units, e.g. metres):",
            2.0, 0.001, 100000.0, 3)
        if not ok2:
            return None
        radius = height / math.tan(math.radians(angle_deg))
        diameter = 2.0 * radius

    elif choice.startswith("Height"):
        angle_deg, ok1 = QInputDialog.getDouble(
            None, "Angle of Repose", "Angle of repose (degrees, e.g. 34):",
            34.0, 0.1, 89.9, 2)
        if not ok1:
            return None
        diameter, ok2 = QInputDialog.getDouble(
            None, "Diameter", "Mound base diameter (map units, e.g. metres):",
            10.0, 0.001, 1000000.0, 3)
        if not ok2:
            return None
        radius = diameter / 2.0
        height = radius * math.tan(math.radians(angle_deg))

    else:  # Angle of Repose
        height, ok1 = QInputDialog.getDouble(
            None, "Height", "Mound height (map vertical units, e.g. metres):",
            2.0, 0.001, 100000.0, 3)
        if not ok1:
            return None
        diameter, ok2 = QInputDialog.getDouble(
            None, "Diameter", "Mound base diameter (map units, e.g. metres):",
            10.0, 0.001, 1000000.0, 3)
        if not ok2:
            return None
        radius = diameter / 2.0
        angle_deg = math.degrees(math.atan(height / radius))

    return angle_deg, height, diameter


def ask_talus_exponent():
    """Ask how concave the talus profile should be.
    n = 1.0  -> straight-sided cone (constant slope = angle of repose)
    n > 1.0  -> concave talus profile: steep near the crest, easing out
                to a smooth, near-zero slope at the toe. 1.5-2.0 is a
                reasonable starting point for a natural-looking scree pile.
    """
    n, ok = QInputDialog.getDouble(
        None, "Talus Profile",
        "Talus concavity exponent\n"
        "(1.0 = straight-line cone, higher = more concave/curved toe,\n"
        "typical range 1.3 - 2.5):",
        1.6, 1.0, 5.0, 2
    )
    if not ok:
        return None
    return n


def build_output_path(src_path):
    """Ask the user where to save the new DEM; default = <name>_mound.tif
    next to the original."""
    base, ext = os.path.splitext(src_path)
    if not ext:
        ext = ".tif"
    default_path = base + "_mound" + ext

    out_path, _ = QFileDialog.getSaveFileName(
        None, "Save Modified DEM As", default_path,
        "GeoTIFF (*.tif *.tiff);;All files (*)"
    )
    return out_path or default_path


# --------------------------------------------------------------------------- #
# Core raster logic
# --------------------------------------------------------------------------- #

def add_mound_to_dem(dem_path, out_path, center_x, center_y, height, radius,
                      talus_exponent=1.6):
    """Reads dem_path with GDAL, adds a talus-profile mound of given
    height/radius centered at (center_x, center_y) in the DEM's own CRS,
    and writes the result to out_path (same georeferencing, nodata, and
    data type).

    Profile: offset(r) = height * (1 - r/radius) ** talus_exponent
    for r <= radius, else 0. This always equals `height` at the center
    and 0 exactly at `radius`; talus_exponent > 1 bows the curve so it's
    steepest near the crest and flattens out toward the toe (concave,
    like a real scree/talus pile) instead of a constant-angle cone."""

    src_ds = gdal.Open(dem_path, gdal.GA_ReadOnly)
    if src_ds is None:
        raise RuntimeError("Could not open DEM: {}".format(dem_path))

    gt = src_ds.GetGeoTransform()
    proj = src_ds.GetProjection()
    band = src_ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    dtype = band.DataType
    x_size = src_ds.RasterXSize
    y_size = src_ds.RasterYSize

    px_w = gt[1]
    px_h = gt[5]  # usually negative

    # World -> pixel for the mound center
    inv_ok, inv_gt = gdal.InvGeoTransform(gt)
    if not inv_ok:
        raise RuntimeError("DEM geotransform is not invertible.")
    center_col, center_row = gdal.ApplyGeoTransform(inv_gt, center_x, center_y)

    # Radius expressed in pixels (handle non-square pixels using the average
    # of the absolute x/y pixel sizes)
    avg_px_size = (abs(px_w) + abs(px_h)) / 2.0
    radius_px = radius / avg_px_size

    # Bounding window (with 1 px margin) that contains the mound footprint
    col_min = max(0, int(math.floor(center_col - radius_px - 1)))
    col_max = min(x_size - 1, int(math.ceil(center_col + radius_px + 1)))
    row_min = max(0, int(math.floor(center_row - radius_px - 1)))
    row_max = min(y_size - 1, int(math.ceil(center_row + radius_px + 1)))

    if col_max < col_min or row_max < row_min:
        raise RuntimeError(
            "The selected point's mound footprint falls entirely outside "
            "the DEM extent."
        )

    win_cols = col_max - col_min + 1
    win_rows = row_max - row_min + 1

    # Read only the window we need to modify
    window = band.ReadAsArray(col_min, row_min, win_cols, win_rows).astype(
        np.float64
    )

    # Build a real-world-distance grid for every pixel in the window
    cols = np.arange(col_min, col_max + 1)
    rows = np.arange(row_min, row_max + 1)
    col_grid, row_grid = np.meshgrid(cols, rows)

    # Pixel-center world coordinates
    x_world = gt[0] + (col_grid + 0.5) * gt[1] + (row_grid + 0.5) * gt[2]
    y_world = gt[3] + (col_grid + 0.5) * gt[4] + (row_grid + 0.5) * gt[5]

    dist = np.sqrt((x_world - center_x) ** 2 + (y_world - center_y) ** 2)

    # Talus (concave) profile: full height at center, easing out to 0 at
    # the radius, 0 beyond. talus_exponent > 1 bows the curve concave;
    # talus_exponent == 1 reproduces the straight-line cone.
    norm = np.clip(1.0 - dist / radius, 0.0, None)
    offset = np.where(dist <= radius, height * np.power(norm, talus_exponent), 0.0)

    if nodata is not None:
        valid_mask = window != nodata
        window[valid_mask] = window[valid_mask] + offset[valid_mask]
    else:
        window = window + offset

    # Copy the whole source raster to the destination, then patch the window
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(out_path, x_size, y_size, 1, dtype)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)
    out_band = out_ds.GetRasterBand(1)
    if nodata is not None:
        out_band.SetNoDataValue(nodata)

    # Write full original data first
    full_data = band.ReadAsArray()
    out_band.WriteArray(full_data)

    # Patch in the modified window
    out_band.WriteArray(window.astype(full_data.dtype), col_min, row_min)
    out_band.FlushCache()

    out_ds = None
    src_ds = None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    point_layer = pick_point_layer()
    if point_layer is None:
        return

    dem_layer = pick_dem_layer()
    if dem_layer is None:
        return

    xy = get_selected_point_geom(point_layer)
    if xy is None:
        return
    px, py = xy

    dem_crs = dem_layer.crs()
    px, py = transform_point(px, py, point_layer.crs(), dem_crs)

    params = ask_two_of_three_params()
    if params is None:
        return
    angle_deg, height, diameter = params
    radius = diameter / 2.0

    talus_exponent = ask_talus_exponent()
    if talus_exponent is None:
        return

    _info(
        "Mound parameters:\n"
        "  Angle of repose (crest, avg.): {:.2f} deg\n"
        "  Height:                        {:.3f}\n"
        "  Diameter:                      {:.3f}\n"
        "  Talus exponent:                {:.2f}\n"
        "  Center (DEM CRS): {:.3f}, {:.3f}".format(
            angle_deg, height, diameter, talus_exponent, px, py
        )
    )

    dem_source = dem_layer.source()
    out_path = build_output_path(dem_source)
    if not out_path:
        return

    try:
        add_mound_to_dem(dem_source, out_path, px, py, height, radius,
                          talus_exponent=talus_exponent)
    except Exception as e:
        _warn("Failed to build mound:\n{}".format(e))
        return

    load, ok = QInputDialog.getItem(
        None, "Done", "Mound DEM saved. Load it into the project?",
        ["Yes", "No"], 0, False
    )
    if ok and load == "Yes":
        new_layer = QgsRasterLayer(out_path, os.path.basename(out_path))
        if new_layer.isValid():
            QgsProject.instance().addMapLayer(new_layer)
        else:
            _warn("Saved successfully, but the new layer failed to load.")

    _info("Done. New DEM written to:\n{}".format(out_path))


# Run
main()
