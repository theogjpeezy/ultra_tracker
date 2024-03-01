#!/usr/bin/env python3


from scipy.spatial import KDTree
from urllib.parse import urlencode
import requests

from geo_utils import interpolate_between_points, transform_path


class CaltopoMap:
    """
    An instance of a CalTopo map from https://caltopo.com/. This represents a single map with 0 or
    more map objects.
    """

    def __init__(self, map_id, cookie):
        self.map_id = map_id
        self.cookie = cookie
        self.tracking_folder_id = None
        self.route_id = None
        self.marker_id = None
        self.route = []
        self.distances = []
        self.get_map_data()
        self.start_location = self.route[0]
        self.finish_location = self.route[-1]
        self.kdtree = KDTree(self.route)

    def get(self, url: str) -> dict:
        """
        Perform a GET to the CalTopo API.

        :param str url: The URL on which to issue the GET.
        :return dict: The response dict.
        """
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": self.cookie,
        }
        response = requests.get(url, headers=headers, verify=True)
        return response.json()

    def get_map_data(self):
        """
        Gets all of the data of the CalTopo map, cleans and transforms some of it, and stores it in
        the appropriate attributes.

        :reutrn None:
        """
        map_data = self.get(f"https://caltopo.com/api/v1/map/{self.map_id}/since/0")
        try:
            features = map_data["result"]["state"]["features"]
        except KeyError:
            print(f"unable to find features in {map_data}")
            return
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
                self.route, self.distances = transform_path(ordered_points, 0.11)
            elif (
                feature.get("properties", {}).get("class") == "Marker"
                and feature.get("properties", {}).get("title") == "Aaron"
            ):
                self.marker_id = feature["id"]

    def move_marker(
        self, location: list, marker_course: float, description: str
    ) -> requests.Response:
        """
        Moves the tracker marker to the provided location, updates its description, and rotates it.

        :param list location: The (x, y) coordinates to which the marker should be moved.
        :param float marker_course: The heading (0 - 359) in which the marker should be rotated.
        :param str description: The description to set on the marker.
        :return requests.Reponse: A response object of the issued POST.
        """
        url = f"https://caltopo.com/api/v1/map/{self.map_id}/Marker/{self.marker_id}"
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": self.cookie,
        }
        payload = {
            "json": {
                "type": "Feature",
                "id": self.marker_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [location[1], location[0]],
                },
                "properties": {
                    "title": "Aaron",
                    "description": description,
                    "folderId": self.tracking_folder_id,
                    "marker-size": "1.5",
                    "marker-symbol": "a:4",
                    "marker-color": "A200FF",
                    "marker-rotation": marker_course,
                    "class": "Marker",
                },
            }
        }
        result = requests.post(url, headers=headers, data=urlencode(payload), verify=True)
        print(f"marker move result {result.text}")
        return result
