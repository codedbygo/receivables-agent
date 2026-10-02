"""Test-only SMTP catcher for e2e runs without Mailpit: accepts every message and appends it to a file.
python smtp_sink.py <port> <outfile>"""

import socketserver
import sys


class Handler(socketserver.StreamRequestHandler):
    def reply(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())

    def handle(self) -> None:
        self.reply("220 sink ready")
        while line := self.rfile.readline():
            cmd = line.decode(errors="replace").strip().upper()
            if cmd.startswith(("EHLO", "HELO")):
                self.reply("250 sink")
            elif cmd == "DATA":
                self.reply("354 end with .")
                body = []
                while (chunk := self.rfile.readline()) not in (b".\r\n", b".\n", b""):
                    body.append(chunk.decode(errors="replace"))
                with open(sys.argv[2], "a", encoding="utf-8") as f:
                    f.write("".join(body) + "\n=====\n")
                self.reply("250 queued")
            elif cmd == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("127.0.0.1", int(sys.argv[1])), Handler) as server:
    server.serve_forever()
