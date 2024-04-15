#!/usr/bin/env python3

import argparse
import datetime
import json

from flask import Flask, render_template, request
from models.caltopo import CaltopoMap
from models.course import Course
from models.race import Race, Runner
from models.config import Config

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


@app.route("/", methods=["GET"])
def get_race_stats():
    """
    Renders the webpage for the race statistics and monitoring.

    :return tuple: The rendered HTML page.
    """
    return render_template("race_stats.html", **race.html_stats)


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
config = Config(args.config)
# Create the objects to manage the race.
caltopo_map = CaltopoMap(config.caltopo_map_id, config.caltopo_session_id)
print("created map object...")
course = Course(caltopo_map, config.aid_stations, config.route_name)
print("created course object...")
runner = Runner(caltopo_map, config.tracker_marker_name)
print("created runner object...")
race = Race(
    caltopo_map,
    course.timezone.localize(
        datetime.datetime.strptime(config.start_time, "%Y-%m-%dT%H:%M:%S")
    ),
    ".data_store.json",
    course,
    runner,
)
print("created race object...")
# TODO perform a test to see if it authenticates
app.config["UT_GARMIN_API_TOKEN"] = config.garmin_api_token
app.config["UT_RACE"] = race
print("performing authentication test...")
if not caltopo_map.test_authentication():
    exit(1)
print("authentication test passed...")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
