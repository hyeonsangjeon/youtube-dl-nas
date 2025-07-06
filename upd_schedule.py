import subprocess
from apscheduler.schedulers.blocking import BlockingScheduler

def exec_interval():
    result = subprocess.run(["pip", "install", "-U", "yt-dlp"])
    print('exec subprocess 1hour', result)
sched = BlockingScheduler()
sched.add_job(exec_interval, 'interval', seconds=3600)

sched.start()
