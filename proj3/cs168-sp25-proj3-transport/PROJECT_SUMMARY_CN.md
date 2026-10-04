# CS 168 Project 3：Transport 项目完成总结

## 一、项目目标

本项目实现了一个简化版 TCP 传输层协议。它能够在网络模拟器中完成：

- TCP 三次握手
- 可靠的数据接收与发送
- 按序和乱序数据处理
- ACK 确认
- 接收窗口控制
- 连接关闭
- 丢包重传
- RTT 与 RTO 动态估计

项目实现了可靠传输，但没有实现 TCP 拥塞控制。

主要实现文件是：

```text
ext/cs168p2/student_socket.py
```

## 二、整体工作流程

```text
应用程序
   │
   ├── send()：把数据放入 tx_data
   │
   ▼
maybe_send()：根据窗口和 MSS 切分数据
   │
   ▼
new_packet()：创建 TCP segment
   │
   ▼
tx()：更新发送状态并发往网络
   │
   ▼
网络模拟器
   │
   ▼
rx()：接收 TCP/IP packet
   │
   ├── 检查接收序号
   ├── 处理 ACK
   ├── 处理 payload
   ├── 处理 FIN
   ├── 更新窗口
   └── 必要时发送 ACK
```

## 三、核心数据结构

### 1. 发送控制块 `self.snd`

`TXControlBlock` 维护本地发送方向的序列空间：

- `snd.iss`：初始发送序列号
- `snd.una`：最早尚未确认的序列号
- `snd.nxt`：下一个要发送的序列号
- `snd.wnd`：对方通告的接收窗口

发送窗口中的关键关系是：

```text
已经确认 | 已发送但未确认 | 尚未发送

       snd.una        snd.nxt
```

可发送的剩余空间为：

```text
snd.wnd - (snd.nxt - snd.una)
```

### 2. 接收控制块 `self.rcv`

`RXControlBlock` 维护接收方向的序列空间：

- `rcv.nxt`：下一个期望收到的序列号
- `rcv.wnd`：本地剩余接收缓冲区大小

### 3. 缓冲区

- `tx_data`：应用程序待发送的数据
- `rx_data`：已经按序收到、等待应用程序读取的数据

### 4. 接收队列和重传队列

- `rx_queue`：保存乱序到达的接收数据包
- `retx_queue`：保存已发送但还没有被确认、可能需要重传的数据包

两者用途完全不同：前者服务于 Stage 3，后者服务于 Stage 8。

## 四、TCP 序列号

TCP 序列号是 32 位无符号数，可能发生回绕：

```text
0xFFFFFFFF + 1 = 0x00000000
```

因此项目要求使用 `modulo_math.py` 中的序列号运算：

- `|PLUS|`：加法
- `|MINUS|`：减法
- `|EQ|`、`|NE|`：相等和不等
- `|LT|`、`|LE|`、`|GT|`、`|GE|`：比较

普通状态字符串，例如 `ESTABLISHED`、`FIN_WAIT_1`，则使用普通的 `==` 或 `is` 判断，不能使用序列号模运算。

## 五、各阶段完成内容

### Stage 1：三次握手

完成了客户端建立连接的流程：

```text
CLOSED → SYN_SENT → ESTABLISHED
```

主要工作：

- 发送 SYN；
- SYN 使用初始序列号；
- SYN 占用一个序列号空间；
- 接收 SYN-ACK；
- 更新 `rcv.nxt` 和 `snd.una`；
- 发送第三次握手 ACK。

### Stage 2：接收按序数据

收到序列号等于 `rcv.nxt` 的数据后：

- 更新 `rcv.nxt`；
- 按 payload 长度减少 `rcv.wnd`；
- 将 payload 追加到 `rx_data`；
- 设置待发送 ACK。

乱序数据不能直接交给应用程序。

### Stage 3：接收乱序数据

使用 `rx_queue` 暂存乱序数据包。每次收到数据后：

1. 将合法 packet 放入接收队列；
2. 检查序列号最小的数据包；
3. 如果它正好是 `rcv.nxt`，就取出处理；
4. 如果仍然乱序，发送 ACK 并停止本轮队列处理；
5. 对重叠数据包截去已经接收过的前缀，避免重复数据。

### Stage 4：发送数据

完成了发送数据和 ACK 处理：

- `check_ack()` 区分新 ACK、旧 ACK 和超前 ACK；
- `handle_accepted_ack()` 更新 `snd.una`；
- `maybe_send()` 根据发送窗口和 MSS 切分 payload；
- `tx()` 在首次发送数据后推进 `snd.nxt`。

ACK 判断的核心关系是：

```text
新 ACK：snd.una < seg.ack <= snd.nxt
旧 ACK：seg.ack <= snd.una
超前 ACK：seg.ack > snd.nxt
```

### Stage 5：通告窗口

收到对方 segment 后，使用 `seg.win` 更新：

```text
self.snd.wnd
```

这样发送方不会超过接收方剩余的缓冲区空间。

### Stage 6：被动关闭

对方先发送 FIN 时，状态转换为：

```text
ESTABLISHED → CLOSE_WAIT → LAST_ACK → CLOSED
```

主要工作：

- FIN 占用一个序列号；
- 收到 FIN 后推进 `rcv.nxt`；
- 发送 ACK；
- 进入 `CLOSE_WAIT`；
- 本地 `close()` 时通过 `FinControl` 延迟或发送 FIN；
- 收到确认 FIN 的 ACK 后删除连接状态。

### Stage 7：主动关闭

本地主动关闭时，状态转换可能为：

```text
ESTABLISHED → FIN_WAIT_1
                    ├→ FIN_WAIT_2 → TIME_WAIT → CLOSED
                    ├→ TIME_WAIT → CLOSED
                    └→ CLOSING → TIME_WAIT → CLOSED
```

`FinControl` 负责：

- 记录 FIN 是否已经发送；
- 在发送缓冲区清空后发送 FIN；
- 判断对方 ACK 是否确认了 FIN。

### Stage 8：丢包重传

第一次发送 SYN、FIN 或带 payload 的数据包时：

1. 记录 `p.tx_ts`；
2. 将 packet 加入 `retx_queue`。

收到 ACK 后，从 `retx_queue` 移除被确认的数据包。

定时检查最早的未确认 packet：

```text
self.stack.now - p.tx_ts > self.rto
```

如果超时，使用 `retxed=True` 重传。重传不能再次加入重传队列，也不能重复推进 `snd.nxt`。

### Stage 9：RTT 和 RTO

根据首次发送时间和 ACK 到达时间计算 RTT：

```text
R = 当前时间 - 首次发送时间
```

第一次测量：

```text
srtt = R
rttvar = R / 2
rto = srtt + max(G, K * rttvar)
```

后续测量使用 RFC 6298 的平滑公式更新 `srtt`、`rttvar` 和 `rto`。RTO 需要限制在 `MIN_RTO` 和 `MAX_RTO` 之间。

超时重传时，RTO 进行指数退避，但不超过最大值。

## 六、`FinControl` 的作用

`self.fin_ctrl` 在 `StudentUSocket.__init__()` 中创建：

```text
self.fin_ctrl = FinControl(self)
```

它不是函数，而是一个对象，主要提供：

- `set_pending(next_state)`：表示准备发送 FIN；
- `try_send()`：缓冲区清空后实际发送 FIN；
- `acks_our_fin(ack)`：判断 ACK 是否确认自己的 FIN。

## 七、常见调试经验

### 1. 区分 `seg.seq` 和 `seg.ack`

- `seg.seq`：对方发送方向的序列号；
- `seg.ack`：对方确认你发送方向的序列号。

处理 ACK 时，应围绕 `seg.ack`、`snd.una` 和 `snd.nxt` 判断。

### 2. 区分空 ACK 和带数据的 segment

纯 ACK 的 payload 为空，不应该调用数据处理逻辑，否则可能产生多余 ACK。

### 3. 区分两个队列

```text
rx_queue   → 接收乱序数据
retx_queue → 发送重传数据
```

### 4. 不要在重传时重复更新序列号

`retxed=True` 表示这个 packet 不是首次发送。重传不能再次推进 `snd.nxt`，也不能重新加入 `retx_queue`。

### 5. RTT 是往返时间

如果单向链路延迟是 200 ms，那么 RTT 大约是：

```text
200 ms + 200 ms = 400 ms
```

不能把测得的 RTT 再除以 2。

## 八、测试命令

进入测试目录：

```bash
cd ext/cs168p2
```

运行单个 Stage：

```bash
python autograder.py s1
python autograder.py s5
python autograder.py s9
```

运行全部测试：

```bash
python autograder.py all
```

完成项目后，应该确保 Stage 1–9 的测试都通过。

## 九、项目完成后的整体认识

这个项目的核心不是单独实现某一个函数，而是维护几个相互关联的状态：

```text
TCP 状态机
+ 发送序列空间
+ 接收序列空间
+ 发送/接收缓冲区
+ ACK
+ 接收窗口
+ 重传队列
+ 定时器
```

发送数据时，序列号和窗口决定“能发什么”；
接收数据时，序列号和接收队列决定“能交付什么”；
收到 ACK 时，发送窗口和重传队列向前推进；
连接关闭时，FIN 和状态机共同决定连接何时结束。

至此，项目完成了一个能够建立连接、传输数据、处理乱序和丢包、控制窗口并安全关闭连接的简化 TCP 实现。

## 十、AI 辅助使用与个人反思

### AI 辅助使用情况

在完成项目的过程中，我使用 AI 作为学习和调试辅助工具，主要用途包括：

- 将课程网页中的英文要求解释成中文；
- 结合 starter code 说明各个 Stage 的目标和函数之间的关系；
- 帮助理解 `snd.una`、`snd.nxt`、`rcv.nxt`、ACK 和窗口等概念；
- 阅读自动测试输出，定位异常堆栈、错误行和状态转换问题；
- 解释 `rx_queue`、`retx_queue`、`FinControl` 等辅助结构的用途；
- 在我已经编写代码之后，根据日志提示可能的逻辑错误，而不是直接替我完成整个项目。

我仍然需要自己阅读代码、修改实现、运行测试，并根据测试结果反复验证。AI 的解释主要帮助我把抽象的 TCP 状态变化和具体代码联系起来。

### 对自己不足之处的反思

1. **对发送序列空间的理解不够牢固。**

   一开始没有清楚区分 `snd.una` 和 `snd.nxt`，也曾混淆 `seg.seq` 与 `seg.ack`。后来通过具体的序列号例子才理解 ACK 如何推动发送窗口。

2. **容易只关注当前 Stage，忽略前后阶段的联系。**

   例如 Stage 5 的小窗口暴露了 Stage 4 ACK 处理中的问题，Stage 8 的重传又要求修改 Stage 4 的序列号更新逻辑。今后应该在实现每个函数时，同时考虑它会被哪些后续机制调用。

3. **对不同队列的职责区分不够清楚。**

   曾经把接收乱序数据使用的 `rx_queue` 和发送重传使用的 `retx_queue` 混用，导致丢包后无法正确重传。以后应先整理每个数据结构的所有者、生命周期和用途。

4. **调试时没有先阅读完整 traceback。**

   有时看到“测试超时”就先猜测网络或定时器问题，而没有先检查是否存在无限循环、错误参数或类型错误。更好的顺序应该是先看最底层的异常行，再分析测试结果。

5. **对边界条件考虑不足。**

   例如空 payload、序列号回绕、旧 ACK、超前 ACK、重传包和纯 ACK 都需要特殊处理。TCP 实现不能只在普通数据流情况下正确，还必须在这些边界情况下保持状态一致。

6. **独立验证能力还需要加强。**

   之前比较依赖 AI 逐条解释错误。今后应更多使用日志、状态转换图、序列号表格和最小化测试来自己定位问题，再把 AI 当作交叉检查工具。

总体而言，这次项目让我认识到，可靠传输并不是简单地“发送数据并等待 ACK”，而是要同时维护状态机、序列空间、窗口、缓冲区、队列和定时器。AI 帮助我降低了阅读代码和排查错误的门槛，但真正理解和验证实现仍然需要自己完成。
