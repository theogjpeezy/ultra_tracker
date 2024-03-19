#!/usr/bin/env python3


from scipy.spatial import KDTree
from geopy.distance import geodesic
import numpy as np

from caltopo import CaltopoMarker, CaltopoShape


def interpolate_between_points(points: np.array, interval_distance):
    """
    Interpolate points along a path to ensure that no two consecutive points are more than the
    specified distance apart.

    :param numpy.ndarray points: An array of shape (n, 2) where each row represents a point with
    latitude and longitude coordinates.
    :param float interval_distance: The maximum distance allowed between two consecutive points. If
    the distance between two points is greater than this value, additional points will be
    interpolated to meet the specified interval.

    :return numpy.ndarray: An array of interpolated points with latitude and longitude coordinates.
    """
    interpolated_points = np.empty((0, 2), dtype=float)

    for i in range(len(points) - 1):
        point1 = {"latitude": points[i, 0], "longitude": points[i, 1]}
        point2 = {"latitude": points[i + 1, 0], "longitude": points[i + 1, 1]}

        # Convert latitude and longitude to (lat, lon) tuples
        coords1 = (point1["latitude"], point1["longitude"])
        coords2 = (point2["latitude"], point2["longitude"])

        # Calculate the distance between consecutive points
        distance_between_points = geodesic(coords1, coords2).miles

        # Include the starting point of each segment
        interpolated_points = np.vstack(
            [interpolated_points, [point1["latitude"], point1["longitude"]]]
        )

        # Check if interpolation is needed
        if distance_between_points > interval_distance:
            # Calculate the number of intervals needed
            num_intervals = int(distance_between_points / interval_distance)

            # Calculate the step size for latitude and longitude
            lat_step = (point2["latitude"] - point1["latitude"]) / num_intervals
            lon_step = (point2["longitude"] - point1["longitude"]) / num_intervals

            # Generate interpolated points
            intermediate_array = np.array(
                [
                    [point1["latitude"] + j * lat_step, point1["longitude"] + j * lon_step]
                    for j in range(1, num_intervals + 1)  # Include the last point
                ]
            )

            interpolated_points = np.vstack([interpolated_points, intermediate_array])

    # Include the last point of the original array
    interpolated_points = np.vstack(
        [interpolated_points, [point2["latitude"], point2["longitude"]]]
    )

    return interpolated_points


def transform_path(path_data: list, max_step_size: float) -> tuple:
    """
    Takes a list of coordinate pairs (a list) and performs two operations. The first is to
    interpolate the path so that no two points are more than the `max_step_size` apart. The second
    is to calculate a cumulative sum of the distances between the points.

    :param list path_data: The list of coordinates making up the path.
    :param float max_step_size: The maximum distance allowed between points in the transformed path.
    :return tuple: The newly interpolated path as a numpy array and the array of the cumulative
    distances.
    """
    cumulative_distance = 0
    prev_point = None
    interpolated_path_data = interpolate_between_points(np.array(path_data), max_step_size)
    cumulative_distances_array = np.zeros(len(interpolated_path_data))

    for i, point in enumerate(interpolated_path_data):
        if prev_point is not None:
            geo = geodesic(
                (prev_point[0], prev_point[1], prev_point[2] if len(prev_point) == 3 else 0),
                (point[0], point[1], point[2] if len(point) == 3 else 0),
            )
            distance = geo.miles
            cumulative_distance += distance
        cumulative_distances_array[i] = cumulative_distance
        prev_point = point
    return interpolated_path_data, cumulative_distances_array


class Course:
    def __init__(self, caltopo_map, aid_stations: list, route_name: str):
        self.aid_stations = self.extract_aid_stations(aid_stations, caltopo_map)
        self.route = self.extract_route(route_name, caltopo_map)

    def extract_aid_stations(self, aid_stations: list, caltopo_map):
        # Map each marker's title to the object.
        title_to_marker = {marker.title: marker for marker in caltopo_map.markers}
        try:
            return [
                AidStation(
                    title_to_marker[aid_station["name"]]._feature_dict,
                    caltopo_map.map_id,
                    caltopo_map.session_id,
                    aid_station["mile_mark"],
                )
                for aid_station in aid_stations
            ]
        except KeyError as err:
            raise KeyError(f"aid station '{err.args[0]}' not found in {caltopo_map.markers}")

    def extract_route(self, route_name: str, caltopo_map):
        for shape in caltopo_map.shapes:
            if shape.title == route_name:
                return Route(shape._feature_dict, caltopo_map.map_id, caltopo_map.session_id)
        raise LookupError(f"no shape called '{route_name}' found in shapes: {caltopo_map.shapes}")


class AidStation(CaltopoMarker):
    def __init__(self, feature_dict: dict, map_id: str, session_id: str, mile_mark: float):
        super().__init__(feature_dict, map_id, session_id)
        self.mile_mark = mile_mark


class Route(CaltopoShape):
    def __init__(self, feature_dict: dict, map_id: str, session_id: str):
        super().__init__(feature_dict, map_id, session_id)
        # TODO this doesn't handle 3 long lists.
        self.points, self.distances = transform_path([[y, x] for x, y in self.coordinates], 0.11)
        self.length = self.distances[-1]
        self.start_location = self.points[0]
        self.finish_location = self.points[-1]
        self.kdtree = KDTree(self.points)