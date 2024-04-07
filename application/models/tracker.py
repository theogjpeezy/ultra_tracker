#!/usr/bin/env python3


import datetime


class Ping:
    """
    Represents a single ping payload from the tracker.

    :param dict ping_data: The raw tracker payload.
    """

    __slots__ = {
        "_event",
        "altitude",
        "gps_fix",
        "heading",
        "imei",
        "latitude",
        "longitude",
        "message_code",
        "speed",
        "timestamp",
    }

    def __init__(self, ping_data: dict, timezone):
        self._event = ping_data.get("Events", [{}])[0]
        self.altitude = self._event.get("point", {}).get("altitude", 0.0)
        self.gps_fix = self._event.get("point", {}).get("gpsFix", 0)
        self.heading = self._event.get("point", {}).get("course", 0)
        self.imei = self._event.get("imei")
        self.latitude = self._event.get("point", {}).get("latitude", 0.0)
        self.longitude = self._event.get("point", {}).get("longitude", 0.0)
        self.message_code = self._event.get("messageCode")
        self.speed = self._event.get("point", {}).get("speed", 0.0)
        self.timestamp = self.extract_timestamp(timezone)

    @property
    def latlon(self) -> list:
        """
        The coordinates in (latitude, longitude) order.

        :return list: The coordinates in (latitude, longitude) order.
        """
        return [self.latitude, self.longitude]

    @property
    def lonlat(self) -> list:
        """
        The coordinates in (longitude, latitude) order.

        :return list: The coordinates in (longitude, latitude) order.
        """
        return [self.longitude, self.latitude]

    def extract_timestamp(self, timezone):
        """
        Extracts the timestamp from the event.

        :return datetime.datetime: A datetime object representing the timestamp.
        """
        ts = self._event.get("timeStamp", 0)
        try:
            return datetime.datetime.fromtimestamp(ts, timezone)
        except ValueError:
            return datetime.datetime.fromtimestamp(ts // 1000, timezone)

    def __str__(self):
        return f"PING {self.timestamp} | {self.heading}° | {self.latlon}"
