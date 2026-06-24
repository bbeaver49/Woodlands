import itertools
import math
from qgis.core import (
    QgsProject, QgsPointXY, QgsGeometry, QgsFeature,
    QgsVectorLayer, QgsFields, QgsField
)
from qgis.PyQt.QtCore import QVariant

# Configuration Parameters
ANGLE_THRESHOLD_DEGREES = 10.0


def get_perpendicular_bisector(p1, p2):
    """Returns a tuple containing the bisector geometry, source IDs, and its heading angle."""
    geom1, id1 = p1
    geom2, id2 = p2

    mid_x = (geom1.x() + geom2.x()) / 2.0
    mid_y = (geom1.y() + geom2.y()) / 2.0

    dx = geom2.x() - geom1.x()
    dy = geom2.y() - geom1.y()

    if dx == 0 and dy == 0:
        return None

    perp_dx = -dy
    perp_dy = dx

    angle_rad = math.atan2(perp_dy, perp_dx)
    length_factor = 100000.0

    line_start = QgsPointXY(mid_x - perp_dx * length_factor, mid_y - perp_dy * length_factor)
    line_end = QgsPointXY(mid_x + perp_dx * length_factor, mid_y + perp_dy * length_factor)

    bisector_geom = QgsGeometry.fromPolylineXY([line_start, line_end])
    return (bisector_geom, id1, id2, angle_rad)


# 1. Fetch points from the currently selected layer
input_layer = iface.activeLayer()

if not input_layer or input_layer.geometryType() != 0:
    raise Exception("Please select an active Point Vector Layer in your Layers Panel first.")

id_index = input_layer.fields().indexOf('id')
if id_index == -1:
    raise Exception("The selected layer must have an attribute named 'id'.")

crs_string = input_layer.crs().authid()

# Read all point data
points_data = []
for feature in input_layer.getFeatures():
    geom = feature.geometry()
    if geom and not geom.isEmpty():
        point_id = feature.attribute('id')
        point_id = 0 if point_id is None else int(point_id)
        points_data.append((geom.asPoint(), point_id))

if len(points_data) < 3:
    raise Exception("You need at least 3 points to run this process.")

# 2. Generate chords and perpendicular bisectors
bisectors = []
for p1, p2 in itertools.combinations(points_data, 2):
    bisector_info = get_perpendicular_bisector(p1, p2)
    if bisector_info:
        bisectors.append(bisector_info)

# 3. Create Candidate Center Points layer
intersections_layer = QgsVectorLayer(f"Point?crs={crs_string}", "Candidate Center Points", "memory")
inter_provider = intersections_layer.dataProvider()

fields = QgsFields()
fields.append(QgsField("chord1_p1", QVariant.Int))
fields.append(QgsField("chord1_p2", QVariant.Int))
fields.append(QgsField("chord2_p1", QVariant.Int))
fields.append(QgsField("chord2_p2", QVariant.Int))
inter_provider.addAttributes(fields)
intersections_layer.updateFields()

# 4. Intersect bisectors using the generalized angle filter
inter_features = []
intersection_points_for_centroid = []

for b1, b2 in itertools.combinations(bisectors, 2):
    geom_b1, b1_p1, b1_p2, angle1 = b1
    geom_b2, b2_p1, b2_p2, angle2 = b2

    angle_diff = abs(angle1 - angle2)
    if angle_diff > math.pi:
        angle_diff = (2 * math.pi) - angle_diff
    if angle_diff > math.pi / 2:
        angle_diff = math.pi - angle_diff

    if math.degrees(angle_diff) < ANGLE_THRESHOLD_DEGREES:
        continue

    if len({b1_p1, b1_p2, b2_p1, b2_p2}) < 4:
        continue

    if geom_b1.intersects(geom_b2):
        inter_geom = geom_b1.intersection(geom_b2)
        if inter_geom and inter_geom.wkbType() == 1:
            pt = inter_geom.asPoint()
            intersection_points_for_centroid.append(pt)

            feat = QgsFeature(intersections_layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(pt))
            feat.setAttribute("chord1_p1", b1_p1)
            feat.setAttribute("chord1_p2", b1_p2)
            feat.setAttribute("chord2_p1", b2_p1)
            feat.setAttribute("chord2_p2", b2_p2)
            inter_features.append(feat)

if not inter_features:
    raise Exception("No valid intersections passed the angle filter threshold.")

inter_provider.addFeatures(inter_features)

# 5. Calculate Final Centroid Location
multipoint_geom = QgsGeometry.fromMultiPointXY(intersection_points_for_centroid)
centroid_geom = multipoint_geom.centroid()
estimated_center = centroid_geom.asPoint()

# 6. Statistical Calculations: Average Radius & Spread Distance
total_radius_dist = 0.0
for pt, _ in points_data:
    total_radius_dist += math.sqrt((pt.x() - estimated_center.x()) ** 2 + (pt.y() - estimated_center.y()) ** 2)
avg_radius = total_radius_dist / len(points_data)

sum_sq_diffs = 0.0
for pt in intersection_points_for_centroid:
    sum_sq_diffs += (pt.x() - estimated_center.x()) ** 2 + (pt.y() - estimated_center.y()) ** 2
spread_distance = math.sqrt(sum_sq_diffs / len(intersection_points_for_centroid))

# 7. Create Centroid Layer and populate statistical fields
centroid_layer = QgsVectorLayer(f"Point?crs={crs_string}", "Final Estimated Center (Centroid)", "memory")
cent_provider = centroid_layer.dataProvider()

cent_fields = QgsFields()
cent_fields.append(QgsField("avg_radius", QVariant.Double, "double", 10, 4))
cent_fields.append(QgsField("spread_dist", QVariant.Double, "double", 10, 4))
cent_provider.addAttributes(cent_fields)
centroid_layer.updateFields()

centroid_feature = QgsFeature(centroid_layer.fields())
centroid_feature.setGeometry(centroid_geom)
centroid_feature.setAttribute("avg_radius", avg_radius)
centroid_feature.setAttribute("spread_dist", spread_distance)
cent_provider.addFeatures([centroid_feature])

# 8. Create the Ideal Best-Fit Circle Polygon Layer
circle_layer = QgsVectorLayer(f"Polygon?crs={crs_string}", "Ideal Best-Fit Circle", "memory")
circle_provider = circle_layer.dataProvider()

# Add matching attributes to the circle polygon for quick identification
circle_fields = QgsFields()
circle_fields.append(QgsField("radius", QVariant.Double, "double", 10, 4))
circle_provider.addAttributes(circle_fields)
circle_layer.updateFields()

# Generate a high-density polygon using the centroid point buffered by the calculated average radius
# Using 36 segments ensures the circle geometry looks completely smooth on your canvas
circle_geom = centroid_geom.buffer(avg_radius, 36)

circle_feature = QgsFeature(circle_layer.fields())
circle_feature.setGeometry(circle_geom)
circle_feature.setAttribute("radius", avg_radius)
circle_provider.addFeatures([circle_feature])

# 9. Render All Generated Layers to Map Canvas
QgsProject.instance().addMapLayer(circle_layer)
QgsProject.instance().addMapLayer(intersections_layer)
QgsProject.instance().addMapLayer(centroid_layer)

print("--- Process Complete ---")
print(f"Generated a smooth circle geometry with a radius of {avg_radius:.4f} map units.")
