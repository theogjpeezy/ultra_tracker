#!/usr/bin/env bash
uwsgi uwsgi.ini --pyargv '-c race_config.yml'
