import json
import subprocess
from queue import Queue
from bottle import run, Bottle, request, static_file, response, redirect, template, get
from threading import Thread
from bottle_websocket import GeventWebSocketServer
from bottle_websocket import websocket


class WSAddr:
    def __init__(self):
        self.wsClassVal = ''


app = Bottle()


@get('/')
def dl_queue_list():
    return template("./static/template/login.tpl", msg="")


@get('/login', method='POST')
def dl_queue_login():
    with open('Auth.json') as data_file:
        data = json.load(data_file)  # Auth info, when docker run making file
        req_id = request.forms.get("id")
        req_pw = request.forms.get("myPw")

        if (req_id == data["MY_ID"] and req_pw == data["MY_PW"]):
            response.set_cookie("account", req_id, secret="34y823423b23b4234#$@$@#be")
            redirect("/youtube-dl")
        else:
            return template("./static/template/login.tpl", msg="id or password is not correct")


@get('/youtube-dl')
def dl_queue_list():
    with open('Auth.json') as data_file:
        data = json.load(data_file)

    userNm = request.get_cookie("account", secret="34y823423b23b4234#$@$@#be")
    print("CHK : ", userNm)

    if (userNm == data["MY_ID"]):
        return template("./static/template/index.tpl", userNm=userNm)
    else:
        print("no cookie or fail login")
        redirect("/")


@get('/websocket', apply=[websocket])
def echo(ws):
    while True:
        WSAddr.wsClassVal = ws
        msg = WSAddr.wsClassVal.receive()

        if msg is not None:
            a = 'Started downloading  : '
            a = a + msg
            WSAddr.wsClassVal.send(a)
        else:
            break


@get('/youtube-dl/static/:filename#.*#')
def server_static(filename):
    return static_file(filename, root='./static')


@get('/youtube-dl/q', method='GET')
def q_size():
    return {"success": True, "size": json.dumps(list(dl_q.queue))}


@get('/youtube-dl/q', method='POST')
def q_put():
    url = request.json.get('url')

    if "" != url:
        box = (url, WSAddr.wsClassVal)
        dl_q.put(box)
        return {"success": True, "msg": 'We received your download. Please wait.'}
    else:
        return {"success": False, "msg": "download queue somethings wrong."}


def dl_worker():
    while not done:
        item = dl_q.get()
        download(item)
        dl_q.task_done()


def download(url):
    url[1].send("Started downloading   " + url[0])
    subprocess.run(["youtube-dl", "-o", "./downfolder/.incomplete/%(title)s.%(ext)s", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "--exec", "touch {} && mv {} ./downfolder/", "--merge-output-format", "mp4", url[0]])
    url[1].send("Finished downloading   " + url[0])


dl_q = Queue();
done = False;
dl_thread = Thread(target=dl_worker)
dl_thread.start()

run(host='0.0.0.0', port=8080, server=GeventWebSocketServer)

done = True

dl_thread.join()
