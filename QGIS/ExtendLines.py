from qgis.core import (
    QgsProject,
    QgsFeature,
    QgsVectorLayer,
    QgsGeometry,
    QgsPointXY
)
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.utils import iface

# 1. Get the active map layer
layer = iface.activeLayer()

if not layer:
    raise ValueError("No active layer found. Please select a layer.")

# 2. Get selected features
selected_features = list(layer.selectedFeatures())
if not selected_features:
    raise ValueError("Please select at least one line feature.")

# 3. Show pop-up box to get extension distance from user
distance, ok = QInputDialog.getDouble(
    None,
    "Extend Lines",
    "Enter extension distance (map units):",
    value=50.0,
    decimals=2
)

# Run only if user clicks 'OK'
if ok:
    # 4. Create a new memory (scratch) layer to hold extended lines
    crs_auth_id = layer.crs().authid()
    scratch_layer = QgsVectorLayer(f"LineString?crs={crs_auth_id}", "Extended Lines", "memory")
    provider = scratch_layer.dataProvider()

    # Copy the original layer's fields to the scratch layer
    provider.addAttributes(layer.fields())
    scratch_layer.updateFields()

    new_features = []

    # 5. Loop through each selected feature
    for feature in selected_features:
        geom = feature.geometry()

        # Skip if it is not a line type
        if geom.type() != 1:
            continue

        # Get the line vertices
        points = [pt for pt in geom.vertices()]
        if len(points) < 2:
            continue

        # EXTEND THE START OF THE LINE (Straight line projection)
        pt_start = points[0]
        pt_next = points[1]

        # Calculate straight line direction from second point to first point
        dx_start = pt_start.x() - pt_next.x()
        dy_start = pt_start.y() - pt_next.y()
        len_start = (dx_start ** 2 + dy_start ** 2) ** 0.5

        if len_start > 0:
            # Project straight outward past the start point
            new_start_x = pt_start.x() + (dx_start / len_start) * distance
            new_start_y = pt_start.y() + (dy_start / len_start) * distance
            points[0] = QgsPointXY(new_start_x, new_start_y)

        # EXTEND THE END OF THE LINE (Straight line projection)
        pt_end = points[-1]
        pt_prev = points[-2]

        # Calculate straight line direction from second-to-last point to last point
        dx_end = pt_end.x() - pt_prev.x()
        dy_end = pt_end.y() - pt_prev.y()
        len_end = (dx_end ** 2 + dy_end ** 2) ** 0.5

        if len_end > 0:
            # Project straight outward past the end point
            new_end_x = pt_end.x() + (dx_end / len_end) * distance
            new_end_y = pt_end.y() + (dy_end / len_end) * distance
            points[-1] = QgsPointXY(new_end_x, new_end_y)

        # 6. Create new feature with straight extended geometry
        extended_geom = QgsGeometry.fromPolylineXY(points)

        new_feat = QgsFeature(scratch_layer.fields())
        new_feat.setGeometry(extended_geom)
        new_feat.setAttributes(feature.attributes())

        new_features.append(new_feat)

    # 7. Add extended lines to scratch layer and map
    provider.addFeatures(new_features)
    scratch_layer.updateExtents()
    QgsProject.instance().addMapLayer(scratch_layer)
