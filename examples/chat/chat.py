from bottle import get, template, run
from bottle_websocket import GeventWebSocketServer
from bottle_websocket import websocket

users = set()

@get('/')
def index():
    return template('index')

@get('/websocket', apply=[websocket])
def chat(ws):
    users.add(ws)
    print("[ws get] : ",ws)
    while True:
        msg = ws.receive()
        print("[msg get] : ",msg)
        if msg is not None:
            print("[msg is not None] : ",msg)
            for u in users:
                print("[user] : ",u)
                u.send(msg)
        else:
            break
    users.remove(ws)

run(host='127.0.0.1', port=8080, server=GeventWebSocketServer)
