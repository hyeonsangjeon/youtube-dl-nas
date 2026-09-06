import logging
from bottle import ServerAdapter
from gevent import pywsgi, sleep, spawn
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.logging import create_logger


class DownloadWorkerFailed(RuntimeError):
    """The hosting web process must restart from durable download state."""


class GeventWebSocketServer(ServerAdapter):
    def run(self, handler):
        server = pywsgi.WSGIServer((self.host, self.port), handler, handler_class=WebSocketHandler)

        if not self.quiet:
            server.logger = create_logger('geventwebsocket.logging')
            server.logger.setLevel(logging.INFO)
            server.logger.addHandler(logging.StreamHandler())

        worker_failed = self.options.get("worker_failed_event")

        def stop_after_worker_failure():
            while not worker_failed.is_set():
                sleep(0.05)
            server.stop(timeout=1)

        watcher = spawn(stop_after_worker_failure) if worker_failed is not None else None
        try:
            server.serve_forever()
        finally:
            if watcher is not None:
                watcher.kill()
        if worker_failed is not None and worker_failed.is_set():
            raise DownloadWorkerFailed("Download worker failed; process restart is required")
