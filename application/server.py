#!/usr/bin/env python3

import argparse
import datetime
import json

import yaml
from flask import Flask, request
from jinja2 import Environment, FileSystemLoader
from models.caltopo import CaltopoMap
from models.course import Course
from models.race import Race, Runner

app = Flask(__name__)


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


def get_config_data(file_path: str) -> dict:
    """
    Reads in a yaml file and returns the dict.

    :param str file_path: The path to the file.
    :return dict: The parsed dict from the config file.
    """
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


@app.route("/", methods=["GET"])
def get_race_stats():
    """
    Renders the webpage for the race statistics and monitoring.

    :return tuple: The rendered HTML page.
    """
    # Load the Jinja environment and specify the template directory
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("race_stats.html")
    # Render the template with the provided data
    rendered_html = template.render(**race.html_stats)
    # Send the HTML response
    return rendered_html, 200, {"Content-Type": "text/html"}


@app.route("/", methods=["POST"])
def post_data():
    """
    Receives a ping from the tracker, updates the race object, and logs information.

    :return tuple: The HTTP response.
    """
    if request.headers.get("x-outbound-auth-token") != app.config["UT_GARMIN_API_TOKEN"]:
        return "Invalid or missing auth token", 401
    content_length = request.headers.get("Content-Length", 0)
    if not content_length:
        return "Content-Length header is missing or zero", 411
    post_data = request.get_data(as_text=True)
    with open("./.post_log.txt", "a") as file:
        file.write(post_data + "\n")
    race = app.config["UT_RACE"]
    race.ingest_ping(json.loads(post_data))
    return "OK", 200


# Read in the config file.
args = parse_args()
config_data = get_config_data(args.config)
# Create the objects to manage the race.
caltopo_map = CaltopoMap(config_data["caltopo_map_id"], config_data["caltopo_session_id"])
print("created map object...")
course = Course(caltopo_map, config_data["aid_stations"], config_data["route_name"])
print("created course object...")
runner = Runner(caltopo_map, config_data["tracker_marker_name"])
print("created runner object...")
race = Race(
    caltopo_map,
    course.timezone.localize(
        datetime.datetime.strptime(config_data["start_time"], "%Y-%m-%dT%H:%M:%S")
    ),
    ".data_store.json",
    course,
    runner,
)
print("created race object...")
# TODO perform a test to see if it authenticates
app.config["UT_GARMIN_API_TOKEN"] = config_data["garmin_api_token"]
app.config["UT_RACE"] = race
print("performing authentication test...")
if not caltopo_map.test_authentication():
    exit(1)
print("authentication test passed...")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
