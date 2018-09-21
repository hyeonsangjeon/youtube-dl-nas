#!/bin/bash

subber /usr/src/app/Auth.json

python -u /usr/src/app/youtube-dl-server.py
