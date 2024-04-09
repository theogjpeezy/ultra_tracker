#!/usr/bin/env python3


import datetime

import numpy as np
from geopy.distance import geodesic
from scipy.spatial import KDTree

from .caltopo import CaltopoMarker, CaltopoShape, get_timezone


def interpolate_and_filter_points(
    coordinates: np.array, min_interval_dist: float, max_interval_dist: float
):
    """
    Interpolate points between the given coordinates and filter points based on the distance criteria.

    :param numpy.ndarray coordinates: An array of shape (n, 2) where each row represents a point with
    latitude and longitude coordinates.
    :param float min_interval_dist: The minimum distance allowed between two consecutive points. If
    the distance between two points is less than this value, the point will be removed.
    :param float max_interval_dist: The maximum distance allowed between two consecutive points. If
    the distance between two points is greater than this value, additional points will be
    interpolated to meet the specified interval.

    :return numpy.ndarray: An array of filtered and interpolated points with latitude and longitude coordinates.
    """
    interpolated_points = np.empty((0, 2), dtype=float)

    for i in range(len(coordinates) - 1):
        point1 = {"latitude": coordinates[i, 0], "longitude": coordinates[i, 1]}
        point2 = {"latitude": coordinates[i + 1, 0], "longitude": coordinates[i + 1, 1]}

        # Convert latitude and longitude to (lat, lon) tuples
        coords1 = (point1["latitude"], point1["longitude"])
        coords2 = (point2["latitude"], point2["longitude"])

        # Calculate the distance between consecutive points
        distance_between_points = geodesic(coords1, coords2).miles
        # Include the starting point of each segment
        interpolated_points = np.vstack(
            [interpolated_points, [point1["latitude"], point1["longitude"]]]
        )
        # Check if interpolation or removal is needed
        if distance_between_points > max_interval_dist:
            # Calculate the number of intervals needed
            num_intervals = int(distance_between_points / max_interval_dist)
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
        elif distance_between_points < min_interval_dist:
            # Skip adding this point if it's too close to the previous one
            continue
    # Include the last point of the original array
    interpolated_points = np.vstack(
        [interpolated_points, [point2["latitude"], point2["longitude"]]]
    )
    return interpolated_points


def transform_path(path_data: list, min_step_size: float, max_step_size: float) -> tuple:
    """
    Takes a list of coordinate pairs (a list) and performs two operations. The first is to
    interpolate the path so that no two points are more than the `max_step_size` apart. The second
    is to calculate a cumulative sum of the distances between the points.

    :param list path_data: The list of coordinates making up the path.
    :param float min_step_size: The minumum distance allowed between points in the transformed path.
    :param float max_step_size: The maximum distance allowed between points in the transformed path.
    :return tuple: The newly interpolated path as a numpy array and the array of the cumulative
    distances.
    """
    cumulative_distance = 0
    prev_point = None
    interpolated_path_data = interpolate_and_filter_points(
        np.array(path_data), min_step_size, max_step_size
    )
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
    """
    A course is a representation of the race's route, aid stations, and other physical attributes.

    :param CaltopoMap caltopo_map: A CaltopoMap object containing the course and features.
    :param list aid_stations: A list of dicts of the aid stations. This should include their name
    and mile_mark.
    :param str route_name: The name of the route in the map.
    """

    def __init__(self, caltopo_map, aid_stations: list, route_name: str):
        self.aid_stations = self.extract_aid_stations(aid_stations, caltopo_map)
        self.route = self.extract_route(route_name, caltopo_map)
        self.timezone = get_timezone(self.route.start_location)

    def extract_aid_stations(self, aid_stations: list, caltopo_map) -> list:
        """
        Finds each marker in the CaltopoMap and maps it to an aid station.

        :param list aid_stations: A list of dicts of aid station names and mile marks.
        :param CaltopoMap caltopo_map: A CaltopoMap object.
        :return list: A list of AidStation objects making up the course.
        """
        # Map each marker's title to the object.
        title_to_marker = {marker.title: marker for marker in caltopo_map.markers}
        try:
            aid_objs = sorted(
                [
                    AidStation(
                        title_to_marker[aid_station["name"]]._feature_dict,
                        caltopo_map.map_id,
                        caltopo_map.session_id,
                        aid_station["mile_mark"],
                    )
                    for aid_station in aid_stations
                ]
            )
            prev_mile_mark = 0
            # Now define all of the distances to each aid.
            for aso in aid_objs:
                aso.distance_to = aso.mile_mark - prev_mile_mark
                prev_mile_mark = aso.mile_mark
            return aid_objs
        except KeyError as err:
            raise KeyError(f"aid station '{err.args[0]}' not found in {caltopo_map.markers}")

    def extract_route(self, route_name: str, caltopo_map) -> Route:
        """
        Finds the route in the map and returns the object.

        :param str route_name: The name of the route shape on the map.
        :param CaltopoMap caltopo_map: A CaltopoMap object in which to search for the route.
        :return Route: A Route object representing the course route.
        """
        for shape in caltopo_map.shapes:
            if shape.title == route_name:
                return Route(shape._feature_dict, caltopo_map.map_id, caltopo_map.session_id)
        raise LookupError(f"no shape called '{route_name}' found in shapes: {caltopo_map.shapes}")

    def update_aid_stations(self, runner):
        for aid_station in self.aid_stations:
            aid_station.refresh(runner)


class AidStation(CaltopoMarker):
    """
    This special type of marker represents a race's aid station.
    """

    def __init__(self, feature_dict: dict, map_id: str, session_id: str, mile_mark: float):
        super().__init__(feature_dict, map_id, session_id)
        self.mile_mark = mile_mark
        self.estimated_arrival_time = datetime.datetime.fromtimestamp(0)
        self.distance_to = 0

    @property
    def aid_station_description(self) -> str:
        """
        A human-friendly description for the aid station to be used in Caltopo.

        :return str: A comment string for the Caltopo marker.
        """
        return (
            f"𝗺𝗶𝗹𝗲 𝗺𝗮𝗿𝗸: {round(self.mile_mark, 2)}\n"
            f"𝗘𝗧𝗔: {self.estimated_arrival_time.strftime('%m-%d %H:%M')}\n"
        )

    def refresh(self, runner) -> None:
        """
        Updates the aid station marker on the map with the latest data.

        :param Runner runner: A runner object.
        :return None:
        """
        miles_to_me = self.mile_mark - runner.mile_mark
        if miles_to_me < 0:
            # The runner has already passed this aid station.
            return
        minutes_to_me = datetime.timedelta(minutes=miles_to_me * runner.pace)
        self.estimated_arrival_time = runner.last_ping.timestamp + minutes_to_me
        self.description = self.aid_station_description
        # This must be called this way to work with the uwsgi thread decorator.
        CaltopoMarker.update(self)

    def __lt__(self, other):
        return self.mile_mark < other.mile_mark


class Route(CaltopoShape):
    """
    This subclass of the CaltopoShape represents a race's route.
    """

    def __init__(self, feature_dict: dict, map_id: str, session_id: str):
        super().__init__(feature_dict, map_id, session_id)
        # TODO this doesn't handle 3 long lists.
        self.points, self.distances = transform_path(
            [[y, x] for x, y in self.coordinates], 0.02, 0.05
        )
        self.length = self.distances[-1]
        self.start_location = self.points[0]
        self.finish_location = self.points[-1]
        self.kdtree = KDTree(self.points)
