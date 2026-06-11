# PerimeterX collector 载荷加密规格（实测刻画，逆向进行中）

- 日期：2026-06-11
- 来源：`_instrument_perimeterx.py` 活体插桩（捕获 1438 个 hook 事件，`_px_events.json`）
- 样本：`docs/superpowers/research/_px_payload0_sample.txt`（一个完整 collector payload，b64len=742）

## 已确证的性质

1. **外层 = 标准 Base64**。`payload=<标准base64>`，可直接 `base64.b64decode` 还原字节（742 b64 → 443 字节）。
2. **解码后是「低熵、有结构」的字节流，不是 AES**。这是**决定性好消息**——AES/高熵几乎不可破，而这里：
   - raw[:64] hex：
     ```
     694910461008107571635b7e5e0370785a590f101e105610084910615e424577
     7345075761510f1008105a46464241081d1d5b5440535f571c5a4142405d4657
     ```
   - 字节 `0x10`/`0x08`/`0x0f` 高频重复、值域偏低 → 典型 **XOR / 弱可逆变换** 特征（明文里的高频字符 XOR 固定 key 字节 → 固定密文字节）。
3. **所有 payload 共享固定前缀**（base64 层 `aUkQRhAIEH`，字节层 `69 49 10 46 10 08 10 ...`）→ 明文前缀固定（同一批起始字段），且变换是**位置相关确定性**（同明文同位置→同密文），符合 XOR/流式弱加密。

## 关键排除项

- **`window.btoa` 是红鲱鱼**：collector 调 `btoa` 1353 次，但输入全是 UI 串（`<popup>`/`{}` 等），**与 payload 编码无关**。真 payload 由 **VM 内自定义编码器**生成（自实现 base64 + XOR/变换），不经 `window.btoa`。→ 想 hook 到明文，必须 hook **出口前那一步**（`XMLHttpRequest.send` 已 hook 到最终密文串；需再往里一层 hook 自定义编码函数），或直接破 XOR。

## 下一步攻击向量（Phase 2 / 团队深逆）

按性价比排序：

1. **静态找 XOR key**：在钉死的 `main.min.js` 里搜 XOR 循环（`^` 运算 + 取模索引）与其 key 来源。key 可能是：脚本内固定常量、appId 派生、或每会话 nonce（若在 payload 头部明文携带）。
2. **已知明文攻击**：PerimeterX 明文通常是 JSON/数组结构。若明文以 `{`/`[`/固定字段名开头，用已知明文 XOR 密文头反推 key 前若干字节，再验周期。固定前缀 `69 49 10 46 ...` 是绝佳已知明文锚点。
3. **hook 自定义编码器**：在 `_instrument_perimeterx.py` 的 `HookInjector` 里加一族 hook，包住「`String.fromCharCode` / `charCodeAt` 密集循环」或在 `XMLHttpRequest.send` 处对实参做栈回溯，抓 payload 序列化**前**的明文对象。
4. **VM-oracle 兜底**：若 key 每会话 VM 现算且不可静态复刻，则 solver 内跑隔离 JS 运行时，喂明文行为数据、让真 VM 产出合法密文（对注册流水线仍无浏览器）。

## 复现

```
python -c "import base64; p=open('docs/superpowers/research/_px_payload0_sample.txt').read(); \
raw=base64.b64decode(p+'='*(-len(p)%4)); print(raw[:64].hex())"
```

## 更深一层实测（2026-06-11 续）：是**自定义 base64 字母表**，非标准 base64

进一步分析 payload 字符集发现：它用了 `^ } > \`` 等**非标准 base64 字符**，且**缺** `6 O q u v y` 等标准字符 → 这是 **PerimeterX 经典的自定义 base64 字母表（64 字符乱序置换）**。之前"标准 base64 解码出低熵结构字节"其实是**用错字母表的结果**（标准 b64decode 默认忽略非法字符），并非真明文。

**正确解码链 = 自定义字母表 base64 解码 →（可能还有一层 XOR/变换）→ 明文。** 第一关是**拿到那张 64 字符字母表**。

**字母表提取已试且未果的途径**（`_px_crack.py` / `_px_alphabet_probe.py`）：
- ❌ 静态搜 main.min.js 的字符串字面量（长度 60-70、含全部 payload 字符）→ 0 命中：字母表**不是明文字符串字面量**，VM 内动态构建。
- ❌ 运行时 hook `String.prototype.{charAt,indexOf,charCodeAt,split,slice,...}`（记录 55-70 字符高独特串）→ 0 命中：字母表**不经这些方法访问**，疑似 **bracket 取值 `alphabet[i]`（JS 无法 hook 下标访问）**。
- ❌ hook `Array.join` / `String.fromCharCode` 突发 → 只捕获到**数据字节块**（高位字节噪声），非字母表。

**下一步（深 VM 逆向，团队/调试器活）**：
1. **CDP 调试器断点**：在 `XMLHttpRequest.send` 处下断，沿调用栈上溯到 custom-base64 编码函数，在其作用域里读出 `alphabet` 变量（最直接）。
2. **反混淆 main.min.js 的 base64 例程**：定位形如 `for(...){out+=A[(x>>k)&63]}` 的编码循环，还原 `A`（字母表数组/字符串）的构造。
3. 拿到字母表后：用 `custom_b64decode(payload, alphabet)`（`_px_crack.py` 已实现该函数）验证是否直接出明文；若仍是密文，再做 XOR 层分析（已知明文锚点：固定前缀）。

## 状态

载荷加密：**确认为 自定义base64字母表( + 可能一层XOR )**。字母表静态/常规-hook 均未提取到 → 需**调试器断点或 base64 例程反混淆**（深 VM）。
`custom_b64decode()` 工具已就绪（`_px_crack.py`）；`PayloadDecryptor`（Task 14）待字母表确定后实现（接口已就绪 `analysis/decryptor.py`）。
