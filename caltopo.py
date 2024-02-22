#!/usr/bin/env python3

import requests

from scipy.spatial import KDTree
from geopy.distance import geodesic

import numpy as np


class CaltopoMap:
    def __init__(self, map_id, cookie):
        self.map_id = map_id
        self.cookie = cookie
        self.tracking_folder_id = None
        self.route_id = None
        self.marker_id = None
        self.route = []
        self.distances = []
        self.get_map_data()
        self.kdtree = KDTree(self.route)

    def get(self, url):
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": self.cookie,
        }
        response = requests.get(url, headers=headers, verify=True)
        return response.json()

    def convert_route(self, route_data):
        cumulative_distance = 0
        prev_point = None
        cumulative_distances_array = []

        for point in route_data:
            if prev_point is not None:
                geo = geodesic(
                    (prev_point[0], prev_point[1], prev_point[2] if len(prev_point) == 3 else 0),
                    (point[0], point[1], point[2] if len(point) == 3 else 0),
                )
                distance = geo.miles
                cumulative_distance += distance
            cumulative_distances_array.append(cumulative_distance)
            prev_point = point
        return np.array(route_data), cumulative_distances_array

    def get_map_data(self):
        map_data = self.get(f"https://caltopo.com/api/v1/map/{self.map_id}/since/0")
        try:
            features = map_data["result"]["state"]["features"]
        except KeyError:
            return  # TODO
        for feature in features:
            if (
                feature.get("properties", {}).get("class") == "Folder"
                and feature.get("properties", {}).get("title") == "Live Tracking"
            ):
                self.tracking_folder_id = feature["id"]
            elif (
                feature.get("properties", {}).get("class") == "Shape"
                and feature.get("properties", {}).get("title") == "Route"
            ):
                self.route_id = feature["id"]
                # TODO this doesn't handle 3 long lists.
                ordered_points = [[x, y] for y, x in feature["geometry"]["coordinates"]]
                self.route, self.distances = self.convert_route(ordered_points)
            elif (
                feature.get("properties", {}).get("class") == "Marker"
                and feature.get("properties", {}).get("title") == "Aaron"
            ):
                self.marker_id = feature["id"]
