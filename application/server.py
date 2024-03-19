#!/usr/bin/env python3


from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import datetime
import json
import yaml
import sys
from jinja2 import Environment, FileSystemLoader

from caltopo import CaltopoMap
from race import Race, Runner
from course import Course


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
    def __init__(self, garmin_api_token, race, *args, **kwargs):
        self.garmin_api_token = garmin_api_token
        self.race = race
        self.post_log = "./.post_log.txt"
        super().__init__(*args, **kwargs)

    def do_GET(self):
        # Send a 200 OK response
        self.send_response(200)
        # Set the Content-type header
        self.send_header("Content-type", "text/html")
        # End the headers
        self.end_headers()

        # Load the Jinja environment and specify the template directory
        env = Environment(loader=FileSystemLoader("."))  # TODO
        template = env.get_template("race_stats.html")

        # Render the template with the provided data
        rendered_html = template.render(**self.race.html_stats)

        # Send the HTML response
        self.wfile.write(rendered_html.encode("utf-8"))

    def do_POST(self):
        if self.headers.get("x-outbound-auth-token") != self.garmin_api_token:
            self.send_response(401)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Invalid or missing auth token")
            return
        content_length = int(self.headers.get("Content-Length", 0))
        if not content_length:
            self.send_response(411)
            return
        post_data = self.rfile.read(content_length).decode("utf-8")
        with open(self.post_log, "a") as file:
            file.write(post_data + "\n")
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.race.ingest_ping(json.loads(post_data))
        print(
            f"mile mark {self.race.runner.mile_mark} pace: {self.race.runner.pace} elapsed_time: {self.race.runner.elapsed_time}"
        )


def get_config_data(file_path):
    try:
        with open(file_path, "r") as file:
            yaml_content = yaml.safe_load(file)
        return yaml_content
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except yaml.YAMLError as e:
        print(f"Error: YAML parsing error in '{file_path}': {e}")
        return None


# TODO handle time zones


def main():
    # Read in the config file.
    args = parse_args()
    config_data = get_config_data(args.config)
    # Fail fast if these aren't defined.
    garmin_api_token = config_data["garmin_api_token"]
    start_time = datetime.datetime.strptime(config_data["start_time"], "%Y-%m-%dT%H:%M:%S")
    data_store = config_data.get("data_store", ".data_store.json")
    caltopo_map_id = config_data["caltopo_map_id"]
    caltopo_session_id = config_data["caltopo_session_id"]
    aid_station_list = config_data["aid_stations"]
    route_name = config_data["route_name"]
    tracker_marker_name = config_data["tracker_marker_name"]
    caltopo_map = CaltopoMap(caltopo_map_id, caltopo_session_id)
    print("created map object...")
    course = Course(caltopo_map, aid_station_list, route_name)
    print("created course object...")
    runner = Runner(caltopo_map, tracker_marker_name)
    print("created runner object...")

    race = Race(
        start_time,
        data_store,
        course,
        runner,
    )
    print("created race object...")

    server_address = ("", 8080)  # TODO

    # We "partially apply" the first three arguments to the ExampleHandler
    handler = partial(GarminTrackHandler, garmin_api_token, race)
    # .. then pass it to HTTPHandler as normal:
    server = HTTPServer(server_address, handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
