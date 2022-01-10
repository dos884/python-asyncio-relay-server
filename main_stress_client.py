import random
import socket

from datetime import datetime
import asyncio

SERVER_IP = '127.0.0.1'
# SERVER_IP = '95.216.22.52'
address_tuple = socket.gethostbyname_ex("cubecastle.xyz")
host_ip = address_tuple[2][0]
print(host_ip)
num_dgram_rec = 0
SERVER_PORT_UDP = 9990
SERVER_PORT_TCP = 8888
UDP_USERNAME_CONFIRM = 5
KEEP_ALIVE=4
EOF = "<EOF>"
SEPARATOR = "~"
SERVER_PASS = "alpha_centauri_2077"
class EchoClientProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        global num_dgram_rec
        message = data.decode()
        timestr = datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]
        message = message + f"|rec:({timestr})"
        if num_dgram_rec % 5000 == 0:
            print(f'Received {message!r}')
        num_dgram_rec += 1

num_logged_in =0
async def stress_client(i):
    print(f"starting task {i}")
    is_udp_confirmed = False
    timestr = datetime.utcnow().strftime('%H:%M:%S.%f')
    name = SERVER_PASS+SEPARATOR+f"udp{i}"+EOF
    reader, writer = await asyncio.open_connection(
        SERVER_IP, SERVER_PORT_TCP)
    writer.write(name.encode())
    await writer.drain()
    loop = asyncio.get_running_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: EchoClientProtocol(),
        remote_addr=(SERVER_IP, SERVER_PORT_UDP))
    # send 10 udp packets with name - if server responds ok, else close this method
    for j in range(100):
        transport.sendto(name.encode(), (SERVER_IP, SERVER_PORT_UDP))
    data = await reader.read(10)
    datas = bytearray(data)
    for b in datas:
        if b == UDP_USERNAME_CONFIRM:
            is_udp_confirmed = True
            writer.write(bytes([UDP_USERNAME_CONFIRM]))
            break
    if not is_udp_confirmed:
        print(f"no UDP confirmed: {i}")
        return
    global num_logged_in
    num_logged_in+=1
    while True:
        sleeptime = random.uniform(0.01, 0.03)
        await asyncio.sleep(sleeptime)
        timestr = datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]
        send_str = f"udp{i}| sent:({timestr!r}) "
        transport.sendto(send_str.encode(), (SERVER_IP, SERVER_PORT_UDP))
        writer.write(bytes([KEEP_ALIVE]))


async def num_tasks():
    while True:
        await asyncio.sleep(0.1)
        active = [t for t in asyncio.Task.all_tasks() if not t.done()]
        print(f"active tasks {len(active)}, logged in {num_logged_in}")


async def main():
    asyncio.create_task(num_tasks())
    tasks = []
    for i in range(2500):

        tasks.append(asyncio.create_task(stress_client(i)))
        #await asyncio.sleep(0.001)
    #await asyncio.gather(*(stress_client(i) for i in range(2500)))
    await asyncio.sleep(60)

asyncio.run(main())
