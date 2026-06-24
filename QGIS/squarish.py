import math
import numpy as np
from qgis.core import (
    QgsProject,
    QgsPointXY,
    QgsGeometry,
    QgsFeature,
    QgsField,
    QgsVectorLayer,
    NULL
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant


def calculate_angle(p1, p2, p3):
    """Calculate the interior angle at p2 formed by p1-p2 and p2-p3 in degrees."""
    v1_x, v1_y = p1.x() - p2.x(), p1.y() - p2.y()
    v2_x, v2_y = p3.x() - p2.x(), p3.y() - p2.y()

    dot_product = (v1_x * v2_x) + (v1_y * v2_y)
    mag1 = math.sqrt(v1_x ** 2 + v1_y ** 2)
    mag2 = math.sqrt(v2_x ** 2 + v2_y ** 2)

    if mag1 == 0 or mag2 == 0:
        return 0.0

    cos_angle = dot_product / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


# 1. Get the active vector layer
layer = iface.activeLayer()
if not layer:
    raise Exception("Please select a layer in the Layers Panel.")

# 2. Get the 4 selected features
selected_features = layer.selectedFeatures()
if len(selected_features) != 4:
    raise Exception(f"Please select exactly 4 points. Currently selected: {len(selected_features)}")

# 3. Sort the points by their "id" attribute
points_dict = {}
for f in selected_features:
    point_id = f['id']
    points_dict[point_id] = f.geometry().asPoint()

# Ensure we have ids 1, 2, 3, 4
for i in [1, 2, 3, 4]:
    if i not in points_dict:
        raise Exception(f"Missing point with id {i} in your selection.")

p1 = points_dict[1]
p2 = points_dict[2]
p3 = points_dict[3]
p4 = points_dict[4]

# 4. Compute edge lengths
d12 = p1.distance(p2)
d23 = p2.distance(p3)
d34 = p3.distance(p4)
d41 = p4.distance(p1)
edges = [d12, d23, d34, d41]
total_edge_length = sum(edges)

# 5. Compute diagonal lengths
d13 = p1.distance(p3)
d24 = p2.distance(p4)

# 6. Compute interior angles
a1 = calculate_angle(p4, p1, p2)
a2 = calculate_angle(p1, p2, p3)
a3 = calculate_angle(p2, p3, p4)
a4 = calculate_angle(p3, p4, p1)
angles = [a1, a2, a3, a4]

# 7. Compute centroid using native geometry methods
poly_geom = QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])
centroid_geom = poly_geom.centroid()
centroid_pt = centroid_geom.asPoint()

# 8. Compute distances from vertices to centroid
dist_to_centroid = [
    p1.distance(centroid_pt),
    p2.distance(centroid_pt),
    p3.distance(centroid_pt),
    p4.distance(centroid_pt)
]

# 9. Calculate statistical metrics
std_angles = float(np.std(angles))
std_edges = float(np.std(edges))
std_centroid_dist = float(np.std(dist_to_centroid))
norm_diag_diff = float(abs(d13 - d24) / total_edge_length) if total_edge_length > 0 else 0.0

# 10. Create an in-memory layer to store the resulting centroid point
crs_string = layer.crs().authid()
centroid_layer = QgsVectorLayer(f"Point?crs={crs_string}", "Squarishness_Centroid", "memory")
provider = centroid_layer.dataProvider()

# Setup fields for all attributes
fields = [
    QgsField("std_angle", QVariant.Double),
    QgsField("std_edge", QVariant.Double),
    QgsField("std_dist_c", QVariant.Double),
    QgsField("diag_diff_n", QVariant.Double),
    QgsField("len_1_2", QVariant.Double),
    QgsField("len_2_3", QVariant.Double),
    QgsField("len_3_4", QVariant.Double),
    QgsField("len_4_1", QVariant.Double),
    QgsField("diag_1_3", QVariant.Double),
    QgsField("diag_2_4", QVariant.Double),
    QgsField("tot_edge_l", QVariant.Double),
    QgsField("diag_diff", QVariant.Double),
    QgsField("ang_1", QVariant.Double),
    QgsField("ang_2", QVariant.Double),
    QgsField("ang_3", QVariant.Double),
    QgsField("ang_4", QVariant.Double)
]
provider.addAttributes(fields)
centroid_layer.updateFields()

# Define the user-friendly field aliases mapping
aliases = {
    "std_angle": "StdDev of Interior Angles (°)",
    "std_edge": "StdDev of Edge Lengths",
    "std_dist_c": "StdDev of Distance to Centroid",
    "diag_diff_n": "Normalized Diagonal Difference",
    "len_1_2": "Edge Length 1->2",
    "len_2_3": "Edge Length 2->3",
    "len_3_4": "Edge Length 3->4",
    "len_4_1": "Edge Length 4->1",
    "diag_1_3": "Diagonal Length 1->3",
    "diag_2_4": "Diagonal Length 2->4",
    "tot_edge_l": "Total Edge Length (Perimeter)",
    "diag_diff": "Absolute Diagonal Difference",
    "ang_1": "Interior Angle at Vertex 1 (°)",
    "ang_2": "Interior Angle at Vertex 2 (°)",
    "ang_3": "Interior Angle at Vertex 3 (°)",
    "ang_4": "Interior Angle at Vertex 4 (°)"
}

# Apply the field aliases to the layer's form configuration
for field_name, alias_text in aliases.items():
    field_idx = centroid_layer.fields().indexFromName(field_name)
    if field_idx != -1:
        centroid_layer.setFieldAlias(field_idx, alias_text)

# Collect values matching the field structure
attribute_values = [
    std_angles,
    std_edges,
    std_centroid_dist,
    norm_diag_diff,
    d12,
    d23,
    d34,
    d41,
    d13,
    d24,
    total_edge_length,
    abs(d13 - d24),
    a1,
    a2,
    a3,
    a4
]

# Create the new feature
new_feature = QgsFeature()
new_feature.setGeometry(centroid_geom)
new_feature.setAttributes(attribute_values)

# Add the feature to the layer
provider.addFeatures([new_feature])
centroid_layer.updateExtents()

# 11. Add the new layer to the QGIS Project map canvas
QgsProject.instance().addMapLayer(centroid_layer)

print("Centroid point generated with descriptive field aliases successfully!")
