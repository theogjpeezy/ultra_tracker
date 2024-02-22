#!/usr/bin/env python3

import logging
from logging.handlers import SysLogHandler

# Create a global logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create a SysLogHandler and set its facility (e.g., LOG_USER)
syslog_handler = SysLogHandler(address="/dev/log", facility=SysLogHandler.LOG_USER)

# Optionally set the syslog format
formatter = logging.Formatter("ultra-tracker - %(levelname)s - %(message)s")
syslog_handler.setFormatter(formatter)

# Add the SysLogHandler to the logger
logger.addHandler(syslog_handler)
