import subprocess
from apscheduler.schedulers.blocking import BlockingScheduler

def exec_interval():
    result = subprocess.run(["pip", "install", "-U", "yt-dlp"])
    print('exec subprocess 1day', result)
sched = BlockingScheduler()
sched.add_job(exec_interval, 'interval', seconds=1440)

sched.start()
