# Check that run.py is open-loop, against a stub gateway that serves one request at a time.
#
#   python3 load/test_run.py
import http.server
import json
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run

SERVICE = 0.05


class SerialStub(http.server.BaseHTTPRequestHandler):
    busy = threading.Lock()

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        with self.busy:
            time.sleep(SERVICE)
        body = json.dumps({"choices": [{"message": {"content": "yes"}}]}).encode()
        self.send_response(200)
        self.send_header("X-Route", "local")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class StubServer(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


class OpenLoopTest(unittest.TestCase):
    def setUp(self):
        self.server = StubServer(("127.0.0.1", 0), SerialStub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.gateway = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_overload_shows_up_as_latency_not_as_dispatch_lag(self):
        n, gap = 40, 0.02
        requests = [{"id": i, "task": "yesno", "prompt": "q", "gold": "yes", "deadline": 0.5, "at": i * gap}
                    for i in range(n)]
        trace = {"arrivals": "fixed", "mix": "uniform", "rate": 1 / gap, "seed": 0, "requests": requests}
        rows = run.run(trace, self.gateway, lead=0.2)

        self.assertTrue(all(r["status"] == 200 and r["score"] == 1 for r in rows))
        self.assertLess(max(r["dispatched"] - r["at"] for r in rows), run.MAX_LAG)
        self.assertAlmostEqual(max(r["completed"] for r in rows), n * SERVICE, delta=0.5)
        self.assertGreater(max(r["latency"] for r in rows), (n - 1) * (SERVICE - gap) * 0.8)
        self.assertGreater(sum(r["missed"] for r in rows), n // 2)


if __name__ == "__main__":
    unittest.main()
