#!/usr/bin/env python3
# Hacky script to more efficiently interact with openocd.
#
# Copyright 2017 Edward Wang <edward.c.wang@compdigitec.com>
import socket
import sys

class OpenOCDError(Exception):
    pass

MESSAGE_PROMPT = "client> "
DEBUG = False

def debug(msg):
    if DEBUG:
        print("DEBUG: " + msg)

# Send a message to openocd
# Add "\r\n" newline
def sendMessage(sock, msg):
    debug("Sent message " + msg)
    sock.send((msg + "\r\n").encode())

# Read until the sender has nothing more to send
def readUntilTimeout(sock):
    data = bytearray()
    try:
        while True:
            data += sock.recv(1024)
    except socket.timeout:
        pass
    return data

# Read until "\r> "
_secret_buffer = bytearray()
def readUntilPrompt(sock):
    global _secret_buffer
    index = _secret_buffer.find("\r> ".encode('ascii'))
    while index < 0:
        _secret_buffer += readUntilTimeout(sock)
        index = _secret_buffer.find("\r> ".encode('ascii'))
    reply = _secret_buffer[:index+3]
    _secret_buffer = _secret_buffer[index+3:]
    return reply.decode("cp1252")

# Extract a response
# e.g. 'reg 2 force\r\n\x00x2 (/32): 0x800004D0\r\n\r> '
# should give "x2 (/32): 0x800004D0" as the actual response
def extractResponse(raw_resp):
    assert raw_resp.endswith("\r> ")
    raw_resp = raw_resp[:-3]
    echo, resp = raw_resp.split("\r\n\x00")
    resp = resp.rstrip() # strip any lingering \r\n
    debug("Got reply " + resp)
    return resp

# Send and receive a reply
def sendAndReadReply(sock, msg):
    sendMessage(sock, msg)
    return extractResponse(readUntilPrompt(sock))

# Build openocd commands to load a program and set the stack pointer (sp)
def builder_loadProgram(bin_file, addr=0x20000000, sp=0x80000950):
    return "load_image {bin_file} 0x{addr:08x} bin; reg 2 0x{sp:08x}".format(bin_file=bin_file, addr=addr, sp=sp)

# Halt the core
def haltCore(sock):
    resp = sendAndReadReply(sock, "halt")
    if "target state: halted" not in resp:
        raise OpenOCDError("Could not successfully halt core")

# Create the socket connection to openocd
def connect(host="localhost", port=4444):
    sock = socket.socket()
    sock.settimeout(0.001)
    try:
        sock.connect((host,port))
    except ConnectionRefusedError:
        raise OpenOCDError("Unable to connect to OpenOCD - perhaps it failed to connect via JTAG or it didn't successfully start? (ConnectionRefusedError)")

    # Clear the "Open On-Chip Debugger"
    readUntilTimeout(sock)

    return sock

# Disconnect from openocd
def disconnect(sock):
    sock.close()

def interactive():
    sock = connect()

    # Load test.bin
    sendAndReadReply(sock, builder_loadProgram("test.bin"))
    sendAndReadReply(sock, "step 0x20000000")
    sendAndReadReply(sock, "resume 0x20000000")

    while False:
        reply = sendAndReadReply(sock, "step; reg pc force; reg 2 force; reg 9 force; reg 1 force; reg 15 force; mdw 0x1200f520;")
        if "pc (/32): 0x00000000" in reply:
            break

    message = input(MESSAGE_PROMPT)

    while message != 'q':
        print("'" + sendAndReadReply(sock, message) + "'")

        message = input(MESSAGE_PROMPT)

    disconnect(sock)
    return 0

def loadprogram(progname, run=False):
    sock = connect()

    haltCore(sock)
    resp = sendAndReadReply(sock, builder_loadProgram(progname))
    if "bytes written at address" not in resp:
        raise OpenOCDError("Could not successfully load program (maybe file not found?)")
    if run:
        sendAndReadReply(sock, "resume 0x20000000")

    disconnect(sock)
    return 0

def loadprogramandrun(progname):
    return loadprogram(progname, True)

def main():
    if len(sys.argv) < 2:
        print("No command specified")
        return 1
    if sys.argv[1] == "interactive":
        return interactive()
    if sys.argv[1] == "loadprogram":
        return loadprogram(sys.argv[2])
    if sys.argv[1] == "loadprogramandrun":
        return loadprogramandrun(sys.argv[2])
    print("Invalid client command specified")
    return 1

if __name__ == '__main__':
    sys.exit(main())
