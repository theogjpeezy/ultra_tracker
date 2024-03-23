#!/usr/bin/env python3


import datetime
import json
import os

import numpy as np
from scipy.stats import norm

from .caltopo import CaltopoMarker
from .course import Route
from .tracker import Ping


def format_duration(duration: datetime.timedelta) -> str:
    """
    Formats a duration object as HH:mm'ss"

    :param datetime.timedelta duration: A time duration.
    :return str: The formatted duration.
    """
    total_hours = duration.total_seconds() / 3600
    hours, remainder = divmod(total_hours, 1)
    minutes, remainder = divmod(remainder * 60, 1)
    seconds, _ = divmod(remainder * 60, 1)
    return f"{int(hours)}:{int(minutes):02}'{int(seconds):02}\""


def convert_decimal_pace_to_pretty_format(decimal_pace: float) -> str:
    """
    Formats a running pace in a traditional human format.

    :param float decimal_pace: A running pace in minutes per mile.
    :return str: The formatted pace as mm'ss".
    """
    total_seconds = int(decimal_pace * 60)  # Convert pace to total seconds
    minutes, remainder = divmod(total_seconds, 60)
    seconds, _ = divmod(remainder, 1)
    return f"{minutes}'{seconds:02d}\""


def calculate_most_probable_mile_mark(
    mile_marks: list, elapsed_time: float, average_pace: float
) -> float:
    """
    Given a list of mile marks, calculates the most likely mile mark given the average pace and
    elapsed time.

    :param list mile_marks: A list of mile markers to test.
    :param float elapsed_time: The elapsed time in minutes.
    :param float average_pace: The average pace in minutes per mile.
    :return float: One of the mile marks from the provided list.
    """
    # Constants
    if not average_pace:
        average_speed = 1 / 10
    else:
        average_speed = 1 / average_pace  # Speed in miles per minute
    # Calculate expected distance based on elapsed time and average speed
    expected_distance = elapsed_time * average_speed
    # Calculate standard deviation based on average pace
    standard_deviation = average_pace / 3  # Adjust for variability in pace
    # Calculate probabilities for each mile mark
    probabilities = norm.pdf(mile_marks, loc=expected_distance, scale=standard_deviation)
    # Find the mile mark with the highest probability
    most_probable_mile_mark = mile_marks[np.argmax(probabilities)]
    return most_probable_mile_mark


class Race:
    """
    This object orchestrates a race.

    :param datetime.datetime start_time: The start time of the race.
    :param str data_store: The filepath in which to store data.
    :param Course course: A course object representing the race.
    :param Runner runner: The runner in the race.
    """

    def __init__(
        self,
        start_time,
        data_store,
        course,
        runner,
    ):
        self.course = course
        self.runner = runner
        self.data_store = data_store
        self.start_time = start_time
        self.started = False
        self.last_ping_raw = {}
        self.restore()

    @property
    def stats(self) -> dict:
        """
        The race statistics to be saved.

        :return dict: The race stats for saving including ping count, runner's pace, and last ping
        data.
        """
        return {
            "pace": self.runner.pace,
            "pings": self.runner.pings,
            "last_ping": self.last_ping_raw,
        }

    @property
    def html_stats(self) -> dict:
        """
        Returns generic runner and race stats to be used for a webpage.

        :return dict: Runner and race stats.
        """
        return {
            "avg_pace": convert_decimal_pace_to_pretty_format(self.runner.pace),
            "mile_mark": round(self.runner.mile_mark, 2),
            "elapsed_time": format_duration(self.runner.elapsed_time),
            "last_update": self.runner.last_ping.timestamp.strftime("%m-%d %H:%M"),
            "pings": self.runner.pings,
            "est_finish_date": self.runner.estimated_finish_date.strftime("%m-%d %H:%M"),
            "est_finish_time": format_duration(self.runner.estimated_finish_time),
            "start_time": self.start_time.strftime("%m-%d %H:%M"),
        }

    def save(self) -> None:
        """
        Saves the race stats to a file.

        :return None:
        """
        with open(self.data_store, "w") as f:
            f.write(json.dumps(self.stats))

    def restore(self) -> None:
        """
        Restores the race state from a file.

        :return None:
        """
        if os.path.exists(self.data_store):
            with open(self.data_store, "r") as f:
                data = json.load(f)
                self.runner.pace = data.get("pace", 10)
                self.runner.pings = data.get("pings", 0)
                self.runner.last_ping = Ping(data.get("last_ping_raw", {}))

    def ingest_ping(self, ping_data: dict) -> None:
        """
        Takes a raw ping payload and updates the race and runner with the information.

        :param dict ping_data: The raw data from a tracker ping.
        :return None:
        """
        self.last_ping_raw = ping_data
        ping = Ping(ping_data)
        # Don't do anything if the race hasn't started yet.
        if ping.timestamp < self.start_time:
            print(f"incoming timestamp {ping.timestamp} before race start time {self.start_time}")
            return
        # Don't do anything if the runner has already finished.
        if self.runner.finished:
            print("runner already finished; ignoring ping")
            return
        self.runner.pings += 1
        self.runner.check_in(ping, self.start_time, self.course.route)
        self.course.update_aid_stations(self.runner)
        self.save()


class Runner:
    """
    This represents a single runner of the race.

    :param CaltopoMap caltopo_map: The Caltopo map object that is associated with the course.
    :param str marker_name: The name of the marker representing the runner.
    """

    def __init__(self, caltopo_map, marker_name: str):
        self.elapsed_time = datetime.timedelta(0)
        self.estimated_finish_date = datetime.datetime.fromtimestamp(0)
        self.estimated_finish_time = datetime.timedelta(0)
        self.finished = False
        self.started = False
        self.mile_mark = 0
        self.last_ping = Ping({})
        self.marker = self.extract_marker(marker_name, caltopo_map)
        self.pace = 10
        self.pings = 0

    def extract_marker(self, marker_name: str, caltopo_map) -> CaltopoMarker:
        """
        Given a marker name, extracts the marker from the map object to associate with the runner.

        :param str marker_name: The marker name or title.
        :param CaltopoMap caltopo_map: The map object containing the markers.
        :return CaltopoMarker: The marker representing the runner.
        """
        for marker in caltopo_map.markers:
            if marker.title == marker_name:
                return marker
        raise LookupError(
            f"no marker called '{marker_name}' found in markers: {caltopo_map.markers}"
        )

    def calculate_pace(self) -> float:
        """
        Calculates the average pace of the runner.

        :return float: The pace in minutes per mile.
        """
        return (
            (self.elapsed_time.total_seconds() / 60.0) / self.mile_mark if self.mile_mark else 10.0
        )

    def check_if_started(self) -> None:
        """
        Checks if the runner has started the race yet or not. This can only be triggered if the
        race is ongoing and the runner has progressed more than 100 yards down the course.

        :return None:
        """
        self.started = self.mile_mark > 0.11

    def check_if_finished(self, route) -> None:
        """
        Checks if the runner has finished the race. This will trigger if the runner is within 100
        yards of the finish line.

        :return None:
        """
        if not self.started:
            self.finished = False
        self.finished = abs(route.length - self.mile_mark) < 0.11

    @property
    def in_progress(self) -> bool:
        """
        Returns a bool to indicate if the runner is still on the course

        :return bool: True if the runner is still on the course and False otherwise.
        """
        return self.started and not self.finished

    @property
    def marker_description(self) -> str:
        """
        A nicely formatted string for the runner's map marker.

        :return str: The runner's map marker description.
        """
        return (
            f"𝗹𝗮𝘀𝘁 𝘂𝗽𝗱𝗮𝘁𝗲: {self.last_ping.timestamp.strftime('%m-%d %H:%M')}\n"
            f"𝗺𝗶𝗹𝗲 𝗺𝗮𝗿𝗸: {round(self.mile_mark, 2)}\n"
            f"𝗲𝗹𝗮𝗽𝘀𝗲𝗱 𝘁𝗶𝗺𝗲: {format_duration(self.elapsed_time)}\n"
            f"𝗮𝘃𝗴 𝗽𝗮𝗰𝗲: {convert_decimal_pace_to_pretty_format(self.pace)}\n"
            f"𝗽𝗶𝗻𝗴𝘀: {self.pings}\n"
            f"𝗘𝗙𝗗: {self.estimated_finish_date.strftime('%m-%d %H:%M')}\n"
            f"𝗘𝗙𝗧: {format_duration(self.estimated_finish_time)}"
        )

    def calculate_mile_mark(self, route) -> float:
        """
        Calculates the most likely mile mark of the runner. This is based on the runner's location
        and pace. This will grab the 5 closest points on the course to the runner's ping,
        calculate the probability (given the last pace) that the runner is at one of those points,
        then return the point with the highest probability.

        :param Route route: The route of the course.
        :return float: The most probable mile mark.
        """
        _, matched_indices = route.kdtree.query(self.last_ping.latlon, k=5)
        return calculate_most_probable_mile_mark(
            [route.distances[i] for i in matched_indices],
            self.elapsed_time.total_seconds() / 60,
            self.pace,
        )

    def check_in(self, ping: Ping, start_time: datetime.datetime, route: Route) -> None:
        """
        This method is called when a runner pings. This will update all of the runner's statistics
        as well as update the map.

        :param Ping ping: The runner's ping payload object.
        :param datetime.datetime start_time: The race start time.
        :param Route route: The route of the race.
        :return None:
        """
        self.pings += 1
        last_timestamp = self.last_ping.timestamp
        # Don't update if latest point is older than current point
        if last_timestamp > ping.timestamp:
            print(f"incoming timestamp {ping.timestamp} older than last timestamp {last_timestamp}")
            return
        # At this point the race has started and this is a new ping.
        self.last_ping = ping
        self.elapsed_time = ping.timestamp - start_time
        self.mile_mark = self.calculate_mile_mark(route)
        self.check_if_started()
        if not self.in_progress:
            print(f"race not in progress; started: {self.started} finished: {self.finished}")
            return
        self.pace = self.calculate_pace()
        self.estimated_finish_time = datetime.timedelta(minutes=self.pace * route.length)
        self.estimated_finish_date = start_time + self.estimated_finish_time
        # Now update the marker attributes.
        self.marker.description = self.marker_description
        self.marker.coordinates = ping.lonlat
        self.marker.rotation = round(ping.heading)
        # Issue the POST to update the marker. This must be called this way to work with the uwsgi
        # thread decorator.
        CaltopoMarker.update(self.marker)
        self.check_if_finished(route)
