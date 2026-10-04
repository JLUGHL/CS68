# CS 168 Project 3：Transport 中文项目说明

本文根据课程页面 [Project 3: Transport](https://sp25.cs168.io/proj3/) 和当前 starter code 整理。

## 1. 项目目标

本项目要求实现一个 TCP 传输层协议的子集。需要实现：

- TCP 三次握手
- 按序和乱序数据接收
- 数据发送和 ACK 处理
- 接收窗口控制
- TCP 连接关闭
- 丢包重传
- RTT 和重传超时估计

项目实现可靠传输，但不要求实现拥塞控制。

- Project 3A：Stage 1–5
- Project 3B：Stage 6–9

课程要求主要修改：`ext/cs168p2/student_socket.py`。不要修改其他文件、添加新文件或添加 import，也不要修改 starter code 中标记区域之外的内容。

## 2. 项目整体结构

```text
应用程序
   │
   ▼
StudentUSocket.send()
   │
   ▼
self.tx_data 发送缓冲区
   │
   ▼
maybe_send()
   │
   ▼
new_packet() 创建 TCP 数据包
   │
   ▼
tx() 发送数据包
   │
   ▼
网络模拟器
   │
   ▼
rx() 接收数据包
   ├── 检查序号和窗口
   ├── 处理 ACK
   ├── 处理数据
   ├── 处理 FIN
   └── 必要时发送 ACK
```

主要目录：

- `pox/`：POX 网络模拟器
- `ext/tcpip/`：TCP/IP 网络模拟、数据包和 socket 管理器
- `ext/cs168p2/student_socket.py`：需要实现的 TCP socket
- `ext/cs168p2/tests/`：各个 Stage 的测试配置
- `ext/cs168p2/autograder.py`：本地自动测试程序

核心类是 `student_socket.py` 中的 `StudentUSocket`。

## 3. TCP socket 的核心数据

### 3.1 发送序列空间：`self.snd`

`TXControlBlock` 维护发送方向的状态：

- `snd.iss`：初始发送序列号
- `snd.una`：最早尚未被确认的序列号
- `snd.nxt`：下一个要发送的序列号
- `snd.wnd`：对方通告的发送窗口大小

可以把发送序列空间理解为：

```text
已经确认       已发送但未确认       尚未发送
   │                 │                 │
snd.iss          snd.una            snd.nxt
```

### 3.2 接收序列空间：`self.rcv`

`RXControlBlock` 维护接收方向的状态：

- `rcv.nxt`：下一个期望收到的序列号
- `rcv.wnd`：本地剩余接收缓冲区空间

### 3.3 缓冲区

- `self.tx_data`：应用程序待发送的数据
- `self.rx_data`：已经按序接收、等待应用程序读取的数据

## 4. TCP 数据包和序列号

收到 TCP segment 后常用的字段有：

- `seg.seq`：序列号
- `seg.ack`：确认号
- `seg.win`：对方通告的接收窗口
- `seg.ACK`、`seg.SYN`、`seg.FIN`：标志位
- `seg.payload`：数据内容

TCP 序列号是 32 位并且可能回绕。因此序列号计算必须使用 `modulo_math.py` 提供的运算符：

- `|PLUS|`：序列号加法
- `|MINUS|`：序列号减法
- `|EQ|`、`|NE|`：等于、不等于
- `|LT|`、`|LE|`、`|GT|`、`|GE|`：序列号比较

## 5. 各个 Stage 的任务

### Stage 1：建立连接

涉及：`connect()`、`rx()`、`handle_synsent()`。

完成 TCP 三次握手：

```text
CLOSED → SYN_SENT → ESTABLISHED
```

需要实现：

1. 创建并发送 SYN。
2. 将状态改为 `SYN_SENT`。
3. 注意 SYN 会占用一个序列号。
4. 接收 SYN-ACK，更新 `rcv.nxt` 和 `snd.una`。
5. 确认 ACK 确实确认了自己的 SYN。
6. 设置 `snd.nxt`、进入 `ESTABLISHED` 并准备发送 ACK。

### Stage 2：接收按序数据

涉及：`rx()`、`handle_accepted_seg()`、`handle_accepted_payload()`。

收到按序数据后：

1. 更新 `rcv.nxt`。
2. 减少 `rcv.wnd`。
3. 将 payload 添加到 `rx_data`。
4. 标记需要发送 ACK。

乱序数据暂时不能直接交给应用程序。

### Stage 3：处理乱序数据

使用 `self.rx_queue` 保存乱序 segment。收到新数据时，将其放入队列，然后反复检查序列号最小的数据包：

- 如果它正好是 `rcv.nxt`，取出并处理。
- 如果仍然乱序，保留在队列中并发送 ACK 请求缺失数据。

还要处理重叠 payload，避免重复数据进入 `rx_data`。

### Stage 4：发送数据

涉及：`check_ack()`、`handle_accepted_ack()`、`maybe_send()`、`tx()`。

`send()` 将数据放入 `tx_data`，`maybe_send()` 根据以下条件发送数据：

- 不能超过 `tx_data` 中已有的数据量。
- 不能超过发送窗口允许的未确认数据量。
- 每个 payload 不能超过 MSS。

接收到 ACK 后：

- 新 ACK：处理并更新发送序列空间。
- 旧 ACK：忽略。
- 超过 `snd.nxt` 的 ACK：丢弃。

### Stage 5：接收窗口

涉及：`update_window()`。

对方在 `seg.win` 中通告剩余接收空间。你需要用它更新 `snd.wnd`，避免向对方发送超过其缓冲区容量的数据。

完成 Stage 1–5 后，即完成 Project 3A。

### Stage 6：被动关闭

对方先发送 FIN：

```text
ESTABLISHED → CLOSE_WAIT → LAST_ACK → CLOSED
```

涉及：`handle_accepted_fin()`、`close()`、`check_ack()`。

收到 FIN 后需要：

- 更新 `rcv.nxt`。
- 准备发送 ACK。
- 进入 `CLOSE_WAIT`。

本地之后调用 `close()`，发送 FIN 并进入 `LAST_ACK`；对方确认 FIN 后删除连接状态。

### Stage 7：主动关闭

本地主动调用 `close()`：

```text
ESTABLISHED → FIN_WAIT_1
```

之后可能进入：

- 收到 ACK：`FIN_WAIT_2`
- 收到 FIN-ACK：直接进入 `TIME_WAIT`
- 先收到 FIN：进入 `CLOSING`，等待对方确认自己的 FIN

最终都会经过 `TIME_WAIT`，计时器结束后进入 `CLOSED`。

### Stage 8：超时重传

使用 `self.retx_queue` 保存已经发送但尚未确认的 SYN、FIN 和数据包。

第一次发送时：

1. 记录发送时间。
2. 加入重传队列。

收到 ACK 后移除已确认的数据包。如果最早的数据包超过 RTO 仍未确认，就重新发送。重传时不能再次加入重传队列。

### Stage 9：动态估计 RTO

根据实际 RTT 更新：

- `srtt`：平滑 RTT
- `rttvar`：RTT 波动
- `rto`：重传超时时间

ACK 到达时，根据原始发送时间计算 RTT 并更新这些变量。发生超时重传时，需要增大 RTO，并限制在 `MIN_RTO` 和 `MAX_RTO` 范围内。

## 6. 连接状态总览

```text
建立连接：
CLOSED → SYN_SENT → ESTABLISHED

被动关闭：
ESTABLISHED → CLOSE_WAIT → LAST_ACK → CLOSED

主动关闭：
ESTABLISHED → FIN_WAIT_1
                    ├→ FIN_WAIT_2 → TIME_WAIT → CLOSED
                    ├→ TIME_WAIT → CLOSED
                    └→ CLOSING → TIME_WAIT → CLOSED
```

## 7. 测试方法

进入测试目录：

```bash
cd ext/cs168p2
```

检查环境：

```bash
chmod +x ../../pox.py
python ../../pox.py config=tests/sanity_test.cfg
```

运行某个 Stage：

```bash
python autograder.py s1
python autograder.py s5
python autograder.py s9
```

运行到某个 Stage：

```bash
python autograder.py all 5
```

运行全部测试：

```bash
python autograder.py all
```

测试名称中的 `s2_t4` 表示 Stage 2 的第 4 个测试。建议每完成一个 Stage 就先运行对应测试。

## 8. 推荐实现顺序

```text
Stage 1：握手
   ↓
Stage 2：接收按序数据
   ↓
Stage 3：接收乱序数据
   ↓
Stage 4：发送数据和处理 ACK
   ↓
Stage 5：发送窗口
   ↓
Stage 6：被动关闭
   ↓
Stage 7：主动关闭
   ↓
Stage 8：超时重传
   ↓
Stage 9：动态 RTO
```

理解这个项目的关键是把以下几部分联系起来：

```text
TCP 状态机
+ 发送序列空间
+ 接收序列空间
+ 发送/接收缓冲区
+ ACK
+ 窗口
+ 重传队列
```
