#!/bin/bash

subber /usr/src/app/Auth.json
pip install --upgrade pip
pip install -U -r /usr/src/app/init_update.txt

# Run with nohup to ignore SIGHUP
nohup python -u /usr/src/app/upd_schedule.py > /var/log/scheduler.log 2>&1 &
SCHEDULER_PID=\$!

# Check if the process started correctly
sleep 2
if ps -p \$SCHEDULER_PID > /dev/null; then
    echo "Scheduler started successfully (PID: \$SCHEDULER_PID)"
else
    echo "Scheduler failed to start!"
fi

python -u /usr/src/app/youtube-dl-server.py