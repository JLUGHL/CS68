import argparse
import select
import socket
import typing
import sys
import platform

# === 请勿修改 ===

# SELECT_TIMEOUT 表示在未收到数据包时，select 调用会阻塞多少秒。
# 数值越小，程序越可能在数据包即将到达时就放弃，并误以为路由器没有响应。
# 数值越大，探测无响应路由器时程序的运行速度越慢。实践中，2 秒通常能取得合理结果。
# 测试并不要求这个数值必须是某个特定值；它只会影响实际运行。
SELECT_TIMEOUT = 2

IPPROTO_ICMP = socket.IPPROTO_ICMP

IPPROTO_UDP = socket.IPPROTO_UDP


def ntohl(x):
    return socket.ntohl(x)


def htonl(x):
    return socket.htonl(x)


def htons(x):
    return socket.htons(x)


def ntohs(x):
    return socket.ntohs(x)


def inet_aton(x):
    return socket.inet_aton(x)


def inet_ntoa(x):
    return socket.inet_ntoa(x)


def inet_pton(x, y):
    return socket.inet_pton(x, y)


def inet_ntop(x, y):
    return socket.inet_ntop(x, y)


def gethostbyname(host: str):
    return socket.gethostbyname(host)


class Socket:
    __sock: socket.socket

    # 创建一个用于发送 traceroute 探测包的 UDP 套接字。
    # 初始代码会替你调用此方法。
    @classmethod
    def make_udp(cls):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                             socket.IPPROTO_UDP)
        return cls(sock)

    # 创建一个用于接收 ICMP 响应的 ICMP 套接字。
    # 初始代码会替你调用此方法。
    @classmethod
    def make_icmp(cls):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                 socket.IPPROTO_ICMP)
        except PermissionError:
            if platform.system() != "Darwin":
                print("PermissionError: please run as root.")
                sys.exit(1)

            # 在 macOS 上可以创建非特权 ICMP 套接字。原始套接字更可靠、跨平台性也更好，
            # 但既然创建失败了，不妨尝试这种方式。
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_ICMP)
        return cls(sock)

    def __init__(self, sock: socket.socket):
        self.__sock = sock

    # 仅用于 UDP 套接字。将此套接字之后发送的所有数据包的 TTL
    # 修改为给定值。
    def set_ttl(self, ttl: int):
        return self.__sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)

    # 仅用于 UDP 套接字。向 `address` 发送 UDP 数据包。
    # `address` 是一个元组，其中包含 IPv4 地址的字符串表示和目标端口。
    # UDP 数据包的负载为 `b`；`sendto` 函数会根据给定信息创建 UDP 数据包头。
    #
    # 参见：https://docs.python.org/3/library/socket.html#socket.socket.sendto
    def sendto(self, b: bytes, address: typing.Tuple[str, int]) -> int:
        return self.__sock.sendto(b, address)

    # 仅用于 ICMP 套接字。从套接字接收一个数据包。
    # 返回包含完整数据包（包括 IP 数据包头）的 `bytes` 对象，
    # 同时返回数据包发送方的地址。
    #
    # 参见：https://docs.python.org/3/library/socket.html#socket.socket.recvfrom
    def recvfrom(self) -> typing.Tuple[bytes, typing.Tuple[str, int]]:
        return self.__sock.recvfrom(4096)

    # 仅用于 ICMP 套接字。阻塞，直到套接字中有数据包可供 `recvfrom()` 接收，
    # 或者 `SELECT_TIMEOUT` 超时。如果 `recvfrom()` 有可接收的数据包，则返回 True。
    #
    # 参见：https://docs.python.org/3/library/select.html#select.select
    def recv_select(self) -> bool:
        rlist, _, _ = select.select([self.__sock], [], [], SELECT_TIMEOUT)
        return rlist != []


def print_result(routers: list[str], ttl: int):
    if len(routers) == 0:
        print(f"{ttl: >2}: *")
        return

    for i, router in enumerate(routers):
        if i == 0:
            preamble = f"{ttl: >2}:"
        else:
            preamble = "   "

        try:
            hostname, _, _ = socket.gethostbyaddr(router)
            print(f"{preamble} {hostname} ({router})")
        except socket.herror:
            print(f"{preamble} {router}")


def parse_args():
    parser = argparse.ArgumentParser(prog='cs168 Traceroute')
    parser.add_argument('host')
    return parser.parse_args()
