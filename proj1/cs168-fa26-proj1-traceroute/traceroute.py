import util

# 程序应发送范围为 [1, TRACEROUTE_MAX_TTL]（含边界）的 TTL。
# 从技术上讲，IPv4 支持最高为 255 的 TTL，但在实际中这个值过大。
# 大多数 traceroute 实现会将上限设置在约 30。单元测试假定你不会修改此数值。
TRACEROUTE_MAX_TTL = 30

# Cisco 似乎已将 UDP 端口 [33434, 33464] 作为 traceroute 的标准端口范围。
# 尽管这不是正式标准，但一些互联网路由器似乎只会对发送到这些端口的 UDP 数据包
# 返回“超时”的 ICMP 消息。最终你可以选择任意端口，不过这个范围通常能得到更有用的结果。
TRACEROUTE_PORT_NUMBER = 33434  # Cisco traceroute 端口号。

# 互联网中的数据包有时会丢失。PROBE_ATTEMPT_COUNT 是 traceroute 函数在放弃并继续之前，
# 尝试探测同一路由器的最大次数。
PROBE_ATTEMPT_COUNT = 3

class IPv4:
    # 下面的每个成员都是 IPv4 数据包头中的一个字段。
    # 它们按字段在数据包中出现的顺序列出。所有字段都应以主机字节序存储。
    #
    # 你只能修改此类的 __init__() 方法。
    version: int
    header_len: int  # 注意：这是以字节为单位的长度，而不是数据包中的字段值。
    tos: int         # 也称为 DSCP 和 ECN 位（参见 Wikipedia）。
    length: int      # 数据包的总长度。
    id: int
    flags: int
    frag_offset: int
    ttl: int
    proto: int
    cksum: int
    src: str
    dst: str

    def __init__(self, buffer: bytes):
        bits = ''.join(format(byte,'08b') for byte in buffer)
        self.version = int(bits[0:4],2)
        self.header_len = int(bits[4:8],2)*4
        self.tos = int(bits[8:16],2)
        self.length = int(bits[16:32],2)
        self.id = int(bits[32:48],2)
        self.flags = int(bits[48:51],2)
        self.frag_offset = int(bits[51:64],2)
        self.ttl = int(bits[64:72],2)
        self.proto = int(bits[72:80],2)
        self.cksum = int(bits[80:96],2)
        self.src = f"{int(bits[96:104], 2)}.{int(bits[104:112], 2)}.{int(bits[112:120], 2)}.{int(bits[120:128], 2)}"
        self.dst = f"{int(bits[128:136], 2)}.{int(bits[136:144], 2)}.{int(bits[144:152], 2)}.{int(bits[152:160], 2)}"

    def __str__(self) -> str:
        return f"IPv{self.version} (tos 0x{self.tos:x}, ttl {self.ttl}, " + \
            f"id {self.id}, flags 0x{self.flags:x}, " + \
            f"offsset {self.frag_offset}, " + \
            f"proto {self.proto}, header_len {self.header_len}, " + \
            f"len {self.length}, cksum 0x{self.cksum:x}) " + \
            f"{self.src} > {self.dst}"


class ICMP:
    # 下面的每个成员都是 ICMP 数据包头中的一个字段。
    # 它们按字段在数据包中出现的顺序列出。所有字段都应以主机字节序存储。
    #
    # 你只能修改此类的 __init__() 方法。
    type: int
    code: int
    cksum: int

    def __init__(self, buffer: bytes):
        bits = ''.join(format(byte,'08b') for byte in buffer)
        self.type = int(bits[0:8],2)
        self.code = int(bits[8:16],2)
        self.cksum = int(bits[16:32],2)
    def __str__(self) -> str:
        return f"ICMP (type {self.type}, code {self.code}, " + \
            f"cksum 0x{self.cksum:x})"


class UDP:
    # 下面的每个成员都是 UDP 数据包头中的一个字段。
    # 它们按字段在数据包中出现的顺序列出。所有字段都应以主机字节序存储。
    #
    # 你只能修改此类的 __init__() 方法。
    src_port: int
    dst_port: int
    len: int
    cksum: int

    def __init__(self, buffer: bytes):
        bits = ''.join(format(byte,'08b') for byte in buffer)
        self.src_port = int(bits[0:16],2)
        self.dst_port = int(bits[16:32],2)
        self.len = int(bits[32:32+16],2)
        self.cksum = int(bits[32+16:32+32],2)

    def __str__(self) -> str:
        return f"UDP (src_port {self.src_port}, dst_port {self.dst_port}, " + \
            f"len {self.len}, cksum 0x{self.cksum:x})"

# TODO 如有需要，可以自由添加辅助函数
def parse_response(packet:bytes, target_ip:str, target_port:int):
    if len(packet) < 20:
        return None
    outer_ip = IPv4(packet)
    if outer_ip.version != 4:
        return None
    if outer_ip.proto != util.IPPROTO_ICMP:
        return None
    icmp_start = outer_ip.header_len
    if len(packet) < icmp_start + 8:
        return None
    icmp = ICMP(packet[icmp_start:icmp_start+8])
    is_ttl_expired = icmp.type == 11 and icmp.code == 0
    is_destination = icmp.type == 3 and icmp.code == 3
    if not (is_ttl_expired or is_destination):
        return None
    inner = icmp_start + 8
    if len(packet) < inner + 20:
        return None
    inner_ip = IPv4(packet[inner:])
    if inner_ip.version != 4:
        return None
    if inner_ip.proto != util.IPPROTO_UDP:
        return None
    if inner_ip.dst != target_ip:
        return None
    udp_start = inner + inner_ip.header_len
    if len(packet) < udp_start + 8:
        return None
    udp = UDP(packet[udp_start:udp_start+8])
    if udp.dst_port != target_port:
        return None
    return outer_ip.src, is_destination
def traceroute(sendsock: util.Socket, recvsock: util.Socket, ip: str) \
        -> list[list[str]]:
    """运行 traceroute 并返回发现的路径。

    对每个 TTL 的探测结果调用 util.print_result()，以显示进度。

    参数：
    sendsock -- 用于发送 traceroute 探测包的 UDP 套接字。
    recvsock -- 用于接收 ICMP 响应的套接字。
    ip -- 要执行 traceroute 的目标主机 IP 地址。

    返回：
    一个列表的列表，表示每个被探测 TTL 所发现的路由器。
    第 i 个列表包含 TTL 为 i+1 的探测所发现的全部路由器，列表中的路由器可以按任意顺序排列。
    如果没有发现路由器，第 i 个列表可以为空。如果发现了 `ip`，应将其作为列表中的最后一个元素。
    """
    results = []
    for ttl in range(1, TRACEROUTE_MAX_TTL+1):
        routers = []
        reached = False
        sendsock.set_ttl(ttl)
        for attempt in range(PROBE_ATTEMPT_COUNT):
            sendsock.sendto(b"",(ip,TRACEROUTE_PORT_NUMBER))
            if recvsock.recv_select():
                packet, sender = recvsock.recvfrom()
                prased = parse_response(packet, ip, TRACEROUTE_PORT_NUMBER)
                if prased is None:
                    continue
                router_ip, reached_destination = prased
                if router_ip not in routers:
                    routers.append(router_ip)
                if reached_destination:
                    reached = True
                    break
        util.print_result(routers, ttl)
        results.append(routers)
        if reached:
            break
    return results


if __name__ == '__main__':
    args = util.parse_args()
    ip_addr = util.gethostbyname(args.host)
    print(f"traceroute to {args.host} ({ip_addr})")
    traceroute(util.Socket.make_udp(), util.Socket.make_icmp(), ip_addr)