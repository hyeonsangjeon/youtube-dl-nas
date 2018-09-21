from bottle import get, run, template
from bottle_websocket import GeventWebSocketServer
from bottle_websocket import websocket

@get('/')
def index():
    return template('index')

@get('/websocket', apply=[websocket])
def echo(ws):
    while True:
        msg = ws.receive()
        print("RECIEVED DATA : "+msg)
        if msg is not None:
            print("msg is not none : "+msg)
            ws.send(msg)
        else:
            print("msg is none : "+msg)
            break

run(host='127.0.0.1', port=8080, server=GeventWebSocketServer)
