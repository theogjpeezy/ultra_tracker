#!/usr/bin/env python3


from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from scipy.stats import norm
import argparse
import datetime
import gpxpy
import json
import numpy as np
import os
import requests
import yaml
from jinja2 import Environment, FileSystemLoader

from caltopo import CaltopoMap, is_within_distance
from service_logging import logger


def parse_args() -> argparse.Namespace:
    """
    Parses the arguments from the command line.

    :return argparse.Namespace: The namespace of the arguments that were parsed.
    """
    p = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="This is a description of my module.",
    )
    p.add_argument(
        "-c", required=True, type=str, dest="config", help="The config file for the event."
    )
    return p.parse_args()


class GarminTrackHandler(BaseHTTPRequestHandler):
    def __init__(self, api_token, race, *args, **kwargs):
        self.api_token = api_token
        self.race = race
        super().__init__(*args, **kwargs)

    def do_GET(self):
        # Send a 200 OK response
        self.send_response(200)
        # Set the Content-type header
        self.send_header("Content-type", "text/html")
        # End the headers
        self.end_headers()

        # Load the Jinja environment and specify the template directory
        env = Environment(loader=FileSystemLoader("/proj/ultra_tracker/"))  # TODO
        template = env.get_template("race_stats.html")

        # Render the template with the provided data
        rendered_html = template.render(**self.race.html_stats)

        # Send the HTML response
        self.wfile.write(rendered_html.encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length).decode("utf-8")
        if self.headers.get("x-outbound-auth-token") != self.api_token:
            logger.critical("Invalid or missing auth token")
            return
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.race.update(json.loads(post_data))
        logger.info(
            f"mile mark {self.race.last_mile_mark} pace: {self.race.pace} elapsed_time: {self.race.elapsed_time}"
        )


def get_config_data(file_path):
    try:
        with open(file_path, "r") as file:
            yaml_content = yaml.safe_load(file)
        return yaml_content
    except FileNotFoundError:
        logger.error(f"Error: File '{file_path}' not found.")
        return None
    except yaml.YAMLError as e:
        logger.error(f"Error: YAML parsing error in '{file_path}': {e}")
        return None


# TODO handle time zones
# TODO handle start/finish
# TODO can we get rid of start time?


class Race:
    def __init__(
        self,
        start_time,
        data_store,
        caltopo_map_id,
        caltopo_cookies,
    ):
        self.caltopo_map = CaltopoMap(caltopo_map_id, caltopo_cookies)
        self.total_distance = self.caltopo_map.distances[-1]
        self.start_time = start_time
        self.last_mile_mark = 0
        self.pace = 10
        self.pings = 0
        self.last_ping = {}
        self.last_timestamp = datetime.datetime.fromtimestamp(0)
        self.elapsed_time = datetime.timedelta(0)
        self.estimated_finish_time = datetime.timedelta(0)
        self.estimated_finish_date = datetime.datetime.fromtimestamp(0)
        self.last_location = (0, 0)
        self.course = 0
        self.data_store = data_store
        self.restore()

    @staticmethod
    def extract_timestamp(ping_data: dict):
        ts = ping_data.get("Events", [{}])[0].get("timeStamp", "0")
        try:
            return datetime.datetime.fromtimestamp(ts)
        except ValueError:
            return datetime.datetime.fromtimestamp(ts // 1000)

    @staticmethod
    def extract_point(ping_data: dict):
        return ping_data.get("Events", [{}])[0].get("point", {})

    @staticmethod
    def extract_course(ping_data: dict):
        return int(Race.extract_point(ping_data).get("course", 0))

    @staticmethod
    def extract_location(ping_data: dict):
        point = Race.extract_point(ping_data)
        return (point.get("latitude", 0), point.get("longitude", 0))

    @property
    def started(self):
        if self.start_time > datetime.datetime.now():
            return False
        return abs(self.total_distance - self.last_mile_mark) > 0.25
        #return is_within_distance(self.last_location, self.caltopo_map.finish_location, 0.25)
        
    @property
    def finished(self):
        if not self.started:
            return False
        return abs(self.total_distance - self.last_mile_mark) < 0.25
        #return is_within_distance(self.last_mile_mark, self.caltopo_map.finish_location, 0.25)

    @property
    def in_progress(self):
        return self.started and not self.finished

    @property
    def stats(self):
        return {"pace": self.pace, "pings": self.pings, "last_ping": self.last_ping}

    @property
    def html_stats(self):
        return {
            "avg_pace": convert_decimal_pace_to_pretty_format(self.pace),
            "mile_mark": round(self.last_mile_mark, 2),
            "elapsed_time": format_duration(self.elapsed_time),
            "last_update": self.last_timestamp.strftime("%m-%d %H:%M"),
            "pings": self.pings,
            "est_finish_date": self.estimated_finish_date.strftime("%m-%d %H:%M"),
            "est_finish_time": format_duration(self.estimated_finish_time),
        }

    @property
    def marker_description(self):
        return (
            f"last update: {self.last_timestamp.strftime('%m-%d %H:%M')}\n"
            f"mile mark: {round(self.last_mile_mark, 2)}\n"
            f"elapsed time: {format_duration(self.elapsed_time)}\n"
            f"avg pace: {convert_decimal_pace_to_pretty_format(self.pace)}\n"
            f"pings: {self.pings}\n"
            f"EFD: {self.estimated_finish_date.strftime('%m-%d %H:%M')}\n"
            f"EFT: {format_duration(self.estimated_finish_time)}"
        )

    def _calculate_last_mile_mark(self):
        _, matched_indices = self.caltopo_map.kdtree.query(self.last_location, k=5)
        return calculate_most_probable_mile_mark(
            [self.caltopo_map.distances[i] for i in matched_indices],
            self.elapsed_time.total_seconds() / 60,
            self.pace,
        )

    def _calculate_pace(self):
        return (
            (self.elapsed_time.total_seconds() / 60.0) / self.last_mile_mark
            if self.last_mile_mark
            else 10
        )

    def save(self):
        with open(self.data_store, "w") as f:
            f.write(json.dumps(self.stats))
        return

    def restore(self):
        if os.path.exists(self.data_store):
            with open(self.data_store, "r") as f:
                data = json.load(f)
                self.pace = data.get("pace", 10)
                self.pings = data.get("pings", 0)
                self.last_ping = data.get("last_ping", {})
        return

    def update(self, ping_data):
        self.pings += 1
        self.last_ping = ping_data
        # Don't update if latest point is older than current point
        if self.last_timestamp > (new_timestamp := self.extract_timestamp(ping_data)):
            logger.info(
                f"incoming timestamp {new_timestamp} older than last timestamp {self.last_timestamp}"
            )
            return
        elif new_timestamp < self.start_time:
            logger.info(
                f"incoming timestamp {new_timestamp} before race start time {self.start_time}"
            )
            return
        self.last_timestamp = new_timestamp
        self.course = self.extract_course(ping_data)
        self.last_location = self.extract_location(ping_data)
        self.elapsed_time = self.last_timestamp - self.start_time
        self.last_mile_mark = self._calculate_last_mile_mark()
        if not self.in_progress:
            return
        self.pace = self._calculate_pace()
        self.estimated_finish_time = datetime.timedelta(minutes=self.pace * self.total_distance)
        self.estimated_finish_date = self.start_time + self.estimated_finish_time
        self.save()
        self.caltopo_map.move_marker(
            self.last_location, self.last_timestamp, self.course, self.marker_description
        )


def format_duration(duration):
    total_hours = duration.total_seconds() / 3600
    hours, remainder = divmod(total_hours, 1)
    minutes, remainder = divmod(remainder * 60, 1)
    seconds, _ = divmod(remainder * 60, 1)
    return f"{int(hours)}:{int(minutes):02}'{int(seconds):02}\""


def convert_decimal_pace_to_pretty_format(decimal_pace):
    total_seconds = int(decimal_pace * 60)  # Convert pace to total seconds
    minutes, remainder = divmod(total_seconds, 60)
    seconds, _ = divmod(remainder, 1)
    pretty_format = f"{minutes}'{seconds:02d}\""
    return pretty_format


def calculate_most_probable_mile_mark(mile_marks, elapsed_time, average_pace):
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






def main():
    # Read in the config file.
    args = parse_args()
    config_data = get_config_data(args.config)
    # Fail fast if these aren't defined.
    api_token = config_data["api_token"]
    start_time = datetime.datetime.strptime(config_data["start_time"], "%Y-%m-%dT%H:%M:%S")
    data_store = config_data["data_store"]
    caltopo_map_id = config_data["caltopo_map_id"]
    caltopo_cookies = config_data["caltopo_cookies"]
    race = Race(
        start_time,
        data_store,
        caltopo_map_id,
        caltopo_cookies,
    )

    server_address = ("", 80)

    # We "partially apply" the first three arguments to the ExampleHandler
    handler = partial(GarminTrackHandler, api_token, race)
    # .. then pass it to HTTPHandler as normal:
    server = HTTPServer(server_address, handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        exit(0)


if __name__ == "__main__":
    main()
