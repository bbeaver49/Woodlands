import numpy as np
from qgis.core import (
    QgsProject,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    Qgis
)
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface

# 1. Get the active map layer
layer = iface.activeLayer()

if not layer:
    raise ValueError("No active layer found. Please select a layer.")

# 2. Get selected features (must select exactly two lines)
features = list(layer.selectedFeatures())

if len(features) != 2:
    raise ValueError("Please select exactly two line features.")

# 3. Get geometries
geom1 = features[0].geometry()
geom2 = features[1].geometry()

# 4. Sample points along the first line to find distances
line1_length = geom1.length()
num_samples = 100
distances = []

for i in range(num_samples + 1):
    # Get point along line 1
    distance_along = (i / num_samples) * line1_length
    point_on_line1 = geom1.interpolate(distance_along)

    # Find shortest distance to line 2
    dist = point_on_line1.distance(geom2)
    distances.append(dist)

# 5. Calculate the average distance
avg_distance = float(np.mean(distances))
print(f"Average distance: {avg_distance}")

# 6. Create parallel offset lines
offset_left = geom1.offsetCurve(0, 1, Qgis.JoinStyle.Round, 2.0)
offset_right = geom1.offsetCurve(-avg_distance, 1, Qgis.JoinStyle.Round, 2.0)

# 7. Create a new memory (scratch) layer
crs_auth_id = layer.crs().authid()
scratch_layer = QgsVectorLayer(f"LineString?crs={crs_auth_id}", "Parallel Offset Lines", "memory")
provider = scratch_layer.dataProvider()

# Add an attribute field to store the calculated distance
provider.addAttributes([QgsField("offset_dist", QVariant.Double)])
scratch_layer.updateFields()

# 8. Create and add features to the scratch layer
feat_left = QgsFeature()
feat_left.setGeometry(offset_left)
feat_left.setAttributes([avg_distance])

feat_right = QgsFeature()
feat_right.setGeometry(offset_right)
feat_right.setAttributes([avg_distance])

provider.addFeatures([feat_left, feat_right])
scratch_layer.updateExtents()

# 9. Add the scratch layer to the QGIS map
QgsProject.instance().addMapLayer(scratch_layer)
