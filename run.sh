#!/bin/bash

subber /usr/src/app/Auth.json
pip install --upgrade pip
pip install -U -r /usr/src/app/init_update.txt
python -u /usr/src/app/upd_schedule.py &
python -u /usr/src/app/youtube-dl-server.py 
