"""
QGIS 3.x Script Console Tool
-----------------------------------------------------------------------------
For a selection of points in a point layer and a selection of line
feature(s) in a line layer, calculates the minimum distance from each
point to the line geometry, stores the results (point id, point name,
distance) in a temporary (memory) layer, and prints summary statistics
(average/mean, standard deviation, maximum, minimum).

USAGE
1. Open the QGIS Python Console (Plugins > Python Console) or the
   Code Editor.
2. Adjust the CONFIGURATION section below if needed (in particular
   NAME_FIELD, which must match a field in your point layer).
3. In the map canvas, select the point(s) you want to measure, and
   select the line feature(s) you want to measure against.
4. Paste/run this script.

NOTES
- "Average" and "mean" are mathematically identical; both are reported
  below for completeness since both were requested.
- If more than one line feature is selected, they are merged into a
  single geometry before measuring, so the reported distance is still
  the minimum distance to the *nearest* part of the selection.
- Distance units follow the CRS of the point layer. If your layer uses
  a geographic CRS (e.g. EPSG:4326), distances will be in degrees, not
  meters. Reproject to a projected CRS first if you need linear units.
-----------------------------------------------------------------------------
"""

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
import statistics

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
POINT_LAYER_NAME = None    # e.g. "MyPoints"; leave None to auto-detect
LINE_LAYER_NAME = None     # e.g. "MyLines";  leave None to auto-detect
NAME_FIELD = "name"        # field in the point layer holding the point's name
OUTPUT_LAYER_NAME = "Point_Line_Distances"
# ---------------------------------------------------------------------------


def find_layer_with_selection(geom_type, forced_name=None):
    """Return the layer matching forced_name, or (if forced_name is None)
    the single layer of the given geometry type that currently has a
    non-empty selection. Raises if the auto-detect is ambiguous."""
    project = QgsProject.instance()
    candidates = []
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        if layer.geometryType() != geom_type:
            continue
        if forced_name:
            if layer.name() == forced_name:
                return layer
            continue
        if layer.selectedFeatureCount() > 0:
            candidates.append(layer)

    if forced_name:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(l.name() for l in candidates)
        raise Exception(
            "Multiple layers of this geometry type have a selection "
            "({}). Set POINT_LAYER_NAME / LINE_LAYER_NAME explicitly.".format(names)
        )
    return None


# ---------------------------------------------------------------------------
# 1. Locate the point layer and line layer
# ---------------------------------------------------------------------------
point_layer = find_layer_with_selection(QgsWkbTypes.PointGeometry, POINT_LAYER_NAME)
line_layer = find_layer_with_selection(QgsWkbTypes.LineGeometry, LINE_LAYER_NAME)

if point_layer is None:
    raise Exception(
        "Could not find a point layer with a selection. "
        "Select some points, or set POINT_LAYER_NAME."
    )
if line_layer is None:
    raise Exception(
        "Could not find a line layer with a selection. "
        "Select a line feature, or set LINE_LAYER_NAME."
    )

point_features = list(point_layer.getSelectedFeatures())
line_features = list(line_layer.getSelectedFeatures())

if not point_features:
    raise Exception("No point features are selected in '{}'.".format(point_layer.name()))
if not line_features:
    raise Exception("No line features are selected in '{}'.".format(line_layer.name()))

# Merge all selected line geometries into one so "distance to the line"
# is measured against the whole selection.
line_geom = QgsGeometry.unaryUnion([f.geometry() for f in line_features])

# ---------------------------------------------------------------------------
# 2. Confirm the name field exists
# ---------------------------------------------------------------------------
field_names = [f.name() for f in point_layer.fields()]
if NAME_FIELD not in field_names:
    print("WARNING: Field '{}' not found in point layer. Available fields: {}".format(
        NAME_FIELD, field_names))
    print("The 'point_name' column will be left blank.")

# ---------------------------------------------------------------------------
# 3. Build the temporary (memory) output layer
# ---------------------------------------------------------------------------
crs_authid = point_layer.crs().authid()
temp_layer = QgsVectorLayer("None?crs={}".format(crs_authid), OUTPUT_LAYER_NAME, "memory")
temp_provider = temp_layer.dataProvider()
temp_provider.addAttributes([
    QgsField("point_id", QVariant.LongLong),
    QgsField("point_name", QVariant.String),
    QgsField("distance", QVariant.Double),
])
temp_layer.updateFields()

# ---------------------------------------------------------------------------
# 4. Calculate minimum distance from each point to the merged line geometry
# ---------------------------------------------------------------------------
distances = []
new_feats = []

for pt_feat in point_features:
    pt_geom = pt_feat.geometry()
    if pt_geom is None or pt_geom.isEmpty():
        continue

    dist = pt_geom.distance(line_geom)  # QgsGeometry.distance() = minimum distance
    distances.append(dist)

    pt_name = pt_feat[NAME_FIELD] if NAME_FIELD in field_names else None

    out_feat = QgsFeature(temp_layer.fields())
    out_feat.setAttributes([pt_feat.id(), pt_name, dist])
    new_feats.append(out_feat)

temp_provider.addFeatures(new_feats)
temp_layer.updateExtents()

# ---------------------------------------------------------------------------
# 5. Add the temporary layer to the project so it can be inspected/exported
# ---------------------------------------------------------------------------
QgsProject.instance().addMapLayer(temp_layer)

# ---------------------------------------------------------------------------
# 6. Compute and report summary statistics
# ---------------------------------------------------------------------------
if distances:
    avg_val = sum(distances) / len(distances)
    mean_val = statistics.mean(distances)
    stdev_val = statistics.stdev(distances) if len(distances) > 1 else 0.0
    max_val = max(distances)
    min_val = min(distances)

    print("=" * 60)
    print("Point-to-Line Minimum Distance Summary")
    print("=" * 60)
    print("Point layer     : {}".format(point_layer.name()))
    print("Line layer      : {}".format(line_layer.name()))
    print("Points measured : {}".format(len(distances)))
    print("-" * 60)
    print("Average distance : {:.4f}".format(avg_val))
    print("Mean distance    : {:.4f}".format(mean_val))
    print("Std deviation    : {:.4f}".format(stdev_val))
    print("Maximum distance : {:.4f}".format(max_val))
    print("Minimum distance : {:.4f}".format(min_val))
    print("=" * 60)
else:
    print("No distances were calculated - check your point/line selections.")