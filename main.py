import asyncio
from enum import Enum
from datetime import datetime

SERVER_IP = '127.0.0.1'
SERVER_IP = '95.216.22.52'
num_dgrams_rec = 0
TCP_PORT = 8888
UDP_PORT = 9990

# class MessageType(Enum):
NONE = 0
GAME_ENDED = 1
GAME_START = 2
YOUR_TURN = 3
KEEP_ALIVE = 4
UDP_USERNAME_CONFIRM = 5
DISCONNECT = 6

# a hashset for connected udp clients
udp_confirmed_set = set()
# username -> WholeClient
username_wc_dict = {}
# this map will contain the results of the matchmaking
username_username_dict = {}
# udpEp -> username
udpEp_username_dict = {}
# todo implement keep alive timers
username_timer_dict = {}


class WholeClient():
    def __init__(self, username, udp_ep=None, tcp_rw=None):
        self.username = username
        self.udp_ep = udp_ep
        # tcp_rw is a reader-writer pair returned by asyncio on connection callback
        self.tcp_rw = tcp_rw
        self.udp_confirmed = False
        # for future use we might want to keep track of whose turn it is
        self.is_myturn = False


class EchoServerProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        global num_dgrams_rec

        if num_dgrams_rec % 5000 == 0:
            print(f'Received (UDP) {len(data)} bytes from {addr}')
        num_dgrams_rec += 1
        if addr not in udp_confirmed_set:
            asyncio.create_task(handle_udp_login(data, addr))
            return
        # if its its a keep alive packet - ignore it
        if len(data) == 1:
            return
        if addr in udpEp_username_dict:
            rec_username = udpEp_username_dict[addr]
            if rec_username in username_wc_dict:
                rec_wc = username_wc_dict[rec_username]
                if rec_wc.udp_confirmed:
                    if rec_username in username_username_dict:
                        if username_username_dict[rec_username] is not None:
                            mapped_username = username_username_dict[rec_username]
                            mapped_ep = username_wc_dict[mapped_username].udp_ep
                            self.transport.sendto(data, mapped_ep)


async def handle_udp_login(data, addr):
    udp_confirmed_set.add(addr)
    username = data.decode().split("~")[0]
    print(f"udp logging username: {username!r}")
    udpEp_username_dict[addr] = username
    if username in username_wc_dict:
        username_wc_dict[username].udp_ep = addr
    else:
        username_wc_dict[username] = WholeClient(username, addr, None)
    while (username in username_wc_dict) and (username_wc_dict[username].tcp_rw is None):
        await asyncio.sleep(0.01)
    if username in username_wc_dict:
        await send_tcp(username, UDP_USERNAME_CONFIRM)
        print(f"binded (UDP) ip {addr} to username: {username!r}")


async def handle_tcp_client(reader, writer):
    # client is new so we know its first message will be a login
    data = await reader.read(2048)
    username = data.decode().split("~")[0]
    if username in username_wc_dict:
        username_wc_dict[username].tcp_rw = (reader, writer)
    else:
        username_wc_dict[username] = WholeClient(username, None, (reader, writer))
    addr = writer.get_extra_info('peername')
    print(f"========== binded (TCP) ip {addr} to username: {username!r}")
    # add a new entry in the match making dict
    username_username_dict[username] = None
    while username in username_wc_dict:
        try:
            print("before read")
            data = await reader.read(256)
            print(f"after read: {len(data)}")
            # print(f"Received {len(data)} from {addr!r}")
            for b in data:
                if b == KEEP_ALIVE:
                    pass
                    # print("got KEEP_ALIVE")

                elif b == UDP_USERNAME_CONFIRM:
                    username_wc_dict[username].udp_confirmed = True
                    print(f"got confirmation for udp login from: {username!r}")
                elif b == DISCONNECT:
                    await disconnect(username)
                    break
                # OR relay tcp message to relayed client
                elif username in username_username_dict:
                    if username_username_dict[username] is not None:
                        relayed_username = username_username_dict[username]
                        await send_tcp(relayed_username, b)

        except ConnectionError as e:
            break

    print(f"closing {addr} connection")
    try:
        writer.close()
    finally:
        return


async def send_tcp(username, byte):
    writer = username_wc_dict[username].tcp_rw[1]
    try:
        writer.write(bytes([byte]))
        await writer.drain()
    except Exception as e:
        print(str(e))


async def disconnect(username):
    print(f"XXXXX closing connection for username {username!r}")
    if username_username_dict[username] is not None:
        mapped_username = username_username_dict[username]
        print(f"{username} was relayed to {mapped_username}")
        username_username_dict[mapped_username] = None
        await send_tcp(mapped_username, GAME_ENDED)
    username_username_dict.pop(username)
    udp_ep = username_wc_dict[username].udp_ep
    udp_confirmed_set.discard(udp_ep)
    udpEp_username_dict.pop(udp_ep)
    username_wc_dict.pop(username)


async def main_tcp():
    server = await asyncio.start_server(
        handle_tcp_client, SERVER_IP, TCP_PORT)

    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')

    async with server:
        await server.serve_forever()


async def main_udp():
    print("Starting UDP server")

    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    # One protocol instance will be created to serve all
    # client requests.
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: EchoServerProtocol(),
        local_addr=(SERVER_IP, UDP_PORT))

    try:
        await asyncio.sleep(3600)  # Serve for 1 hour.
    finally:
        transport.close()


async def main_matchmaker():
    while True:
        await asyncio.sleep(0.5)
        for key in username_username_dict.keys():
            if username_username_dict[key] is None:
                for key2 in username_username_dict.keys():
                    if key != key2 and username_username_dict[key2] is None:
                        if username_wc_dict[key].udp_confirmed and username_wc_dict[key2].udp_confirmed:
                            username_username_dict[key] = key2
                            username_username_dict[key2] = key
                            await send_tcp(key, YOUR_TURN)
                            await send_tcp(key2, GAME_START)
                            break


async def main():
    await asyncio.gather(main_tcp(), main_udp(), main_matchmaker())


asyncio.run(main())
