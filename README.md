# 网易云歌单整理器

把网易云的「我喜欢的音乐」或任意公开歌单，按 **中文 / 英文 / 日语 / 纯音乐** 拆成四个歌单；
自带网页界面，可以再按**语种、曲风、关键词**筛选，筛完直接在页面里写入账号。

![python](https://img.shields.io/badge/python-3.9%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

> 用的是网页版私有接口，不是官方开放平台。只操作自己的账号，注意频率。

---

## 第一步：用 DSH 打开这个项目（推荐）

不用记命令，让 DSH 帮你跑：

1. 启动 **DSH（DeepSeek Harness）**，打开它的 Web 界面，新建一个会话；
2. 把**本仓库所在目录**设为这次会话的工作区（例如 `D:\code\netease-playlist-sorter`）；
3. 在对话框里直接粘贴这句话：

   ```
   读一下 README，帮我把这个项目装好并启动网页：
   pip install -e ".[edge]" 然后 netease-sorter serve，
   起好之后把地址发我，再带我走一遍「登录 → 粘贴歌单链接 → 筛选 → 写歌单」。
   ```

4. DSH 会依次执行安装、启动 `serve`、把 `http://127.0.0.1:8765/` 发给你；
   后面扫码登录、选歌单、写歌单都可以让它带着做，你不用自己敲命令。

> DSH 是一个能读写文件、执行命令、联网查资料的编码智能体，跑在你自己的机器上。
> 登录态和歌单数据都留在本地，不会上传到任何地方。

不想用 DSH 就跳到 [手动安装](#手动安装)，后面的流程是一样的。

---

## 它解决什么问题

网易云没有「按语种自动分类」的功能，喜欢列表攒到几千首之后就是一团乱麻。这个工具把整个流程串起来：

```
拉取曲目 → 取歌词 → 判语种 / 曲风 → 网页里筛选 → 写入歌单
```

实测一个 3759 首的歌单，语种分布是：

| 分类 | 数量 | 主要判定依据 |
|---|---|---|
| 纯音乐 | 1152 | 网易云 `pureMusic` 标记 |
| 英文 | 1374 | 歌词拉丁字母占绝对多数 |
| 日语 | 1192 | 歌词假名占比 ≥ 3% |
| 中文 | 35 | 汉字计分压过拉丁 |
| 其他 | 6 | 韩语 / 俄语，四类里没有归属 |

---

## 三种用法

| 方式 | 适合谁 | 需要什么 |
|---|---|---|
| **DSH**（上面） | 不想碰命令行 | 装好 DSH |
| **网页界面** | 想自己点、自己看 | `netease-sorter serve` |
| **命令行** | 想脚本化 / 定时跑 | `login` + `create` |

### 网页界面

```bash
netease-sorter serve          # http://127.0.0.1:8765
```

纯本地页面，不依赖前端框架、不联网：

| 功能 | 说明 |
|---|---|
| 加载歌单 | 粘贴歌单链接或 id，后台抓取 + 分类，带进度条 |
| 语种筛选 | 中文 / 英文 / 日语 / 纯音乐 / 其他，**可多选**，带数量 |
| 曲风筛选 | 电子、原声、二次元、轻音乐…**可多选**，与语种取交集 |
| 搜索 / 待复核 | 按歌名歌手专辑搜；只留 low / mid 置信度的歌 |
| 勾选与全选 | 勾单曲，或一键全选当前筛选结果 |
| **直接写入账号** | 命令行登录过时，弹窗里一键建歌单 + 写歌，完成给链接 |
| 生成脚本 / 导出 CSV | 没有登录态时的兜底；筛选结果也能导出 |

页面顶部内置 8 步教程，第一次打开会自动展开。

### 命令行

```bash
netease-sorter login --from-edge     # 弹出专用 Edge 窗口，扫码登录
netease-sorter all --playlist 3778678
netease-sorter create --dry-run      # 先看计划
netease-sorter create                # 四类全写
```

`login --from-edge` 会用一个**工具专用的浏览器配置**启动 Edge、等你扫码、通过调试端口把 Cookie 读回来。
第一次要单独登一次，之后直接复用。

> 为什么不直接用你日常的 Edge：Chrome 136 起（Edge 156 同样）在**默认**配置目录上会忽略
> `--remote-debugging-port`，端口根本不开；而复制配置目录又会让 v20 的 Cookie 失效
> （App-Bound Encryption）。专用配置是唯一既能自动读、又不动你日常浏览器的办法。

`create` 的安全约定：

| 情况 | 行为 |
|---|---|
| 同名歌单不存在 | 新建 |
| 同名歌单已存在且为空 | 直接复用 |
| 同名歌单已存在且非空 | **拒绝**，提示加 `--append` 或换名字 |
| 有多个同名歌单 | 报错并列出 id，不猜 |
| 歌单不是你创建的 | 拒绝写入 |
| 中途失败 | 已写入的批次落盘，重跑只补剩下的 |
| 写完 | 重读歌单核对曲目数，并打印歌单链接 |

---

## 手动安装

```bash
git clone https://github.com/MASYER-art/netease-playlist-sorter.git
cd netease-playlist-sorter
pip install -e ".[edge]"
```

- 硬依赖只有 `requests`；
- `[edge]` 装上 `websockets`，`login --from-edge` 要用；
- 想用接口扫码登录（容易被风控）再装 `.[qr]`。

不想安装也能直接跑：

```bash
PYTHONPATH=src python -m netease_sorter --help
```

---

## 快速开始

```bash
# 1. 网页方式：装完直接开，粘贴链接就能用
netease-sorter serve

# 2. 纯公开歌单：不需要登录
netease-sorter all --playlist "https://music.163.com/playlist?id=3778678"

# 3. 我喜欢的音乐：需要登录态
netease-sorter login --from-edge
netease-sorter all --liked
```

跑完 `data/` 下会有：

```
data/
├── library.json      # 曲目 + 歌词缓存
├── meta.json         # 歌单名称、曲目数、更新时间
├── classified.json   # 网页用的分类结果
├── preview.csv       # 全量明细：语种 / 曲风 / 置信度 / 依据
└── 加歌单_纯音乐.js   # 粘到浏览器 Console 即可
```

先看 `preview.csv` 或直接 `serve` 在网页里翻，确认分类靠谱，再执行写入。

---

## 命令说明

| 命令 | 作用 |
|---|---|
| `login` | 保存登录态。`--from-edge` 专用 Edge 窗口扫码；或 `--cookie` / `--cookie-file` |
| `fetch` | 抓曲目和歌词。`--playlist <链接或id>` 或 `--liked`；`--limit N` 试跑 |
| `classify` | 生成 `preview.csv`，打印各类数量与待复核数 |
| `export` | 生成 4 个 Console 脚本 |
| `serve` | 启动本地网页（`--port 8765`，`--no-open` 不自动开浏览器） |
| `create` | 建歌单写入；`--only` / `--name` / `--append` / `--dry-run` |
| `all` | fetch + classify + export |

常用参数：

```bash
netease-sorter create --only 中文,日语                  # 只写这两类
netease-sorter create --only 中文 --name "华语精选"      # 精确指定歌单名（仅单分类）
netease-sorter create --append                          # 允许追加到已存在的非空歌单
netease-sorter serve --port 8800                        # 换端口
```

通用参数 `--data-dir data` 可以换数据目录。歌词会缓存进 `library.json`，重跑只补新增的歌。

---

## 分类是怎么判的

### 语种 / 纯音乐

按优先级，前面的命中就不再往下走：

1. **`pureMusic` 标记** —— 网易云自己标的纯音乐，最可靠；
2. **占位歌词** —— 歌词为「纯音乐，请欣赏」；
3. **强关键词** —— 纯音乐 / instrumental / bgm / 演奏 …（英文词按词边界匹配）；
4. **没有歌词** —— 先看标题里的弱关键词（钢琴、OST、soundtrack…），再按标题文字判语种；
5. **假名占比 ≥ 3%** → 日语；
6. **谚文** → 其他（韩语）；
7. **汉字 vs 拉丁加权计分** → 中文 / 英文，标题权重 ×2。

几个设计上的坑，都写进 `tests/test_classify.py` 了：

- **英文歌常带中文翻译歌词**，直接数汉字会把它们整片判成中文（早期版本中文虚高到 411 首），所以标题权重更高；
- **`ost` 是 `Post Malone` 的子串**，纯 `in` 匹配会误判成 OST 纯音乐，所以英文关键词必须按词边界；
- **没有歌词 ≠ 纯音乐**。未收录歌词的中文/日文歌很多，只有前面几步都判不出来才归纯音乐，并把置信度降为 `mid`/`low`。

输出里带 `置信度` 和 `依据` 两列，`low` / `mid` 的建议人工看一眼。判错了不用改代码：

```csv
# data/overrides.csv
1384026889,纯音乐
5307891,纯音乐
```

### 曲风

网易云接口**不返回曲风字段**，只能用标题 / 歌手 / 专辑里的字符串线索做多标签猜测，
规则集中在 `src/netease_sorter/genres.py` 的 `RULES`。

一条歌可以同时命中多个，比如「TVアニメ…オリジナルサウンドトラック」会同时是 `二次元 + 原声`。

**准确率明显低于语种判定**，别把它当结论，当成筛子用。完全没有线索时按语种兜底：

| 兜底 | 归属 |
|---|---|
| 日语 | `二次元` |
| 纯音乐 | `轻音乐` |
| 其余 | `未标注` |

实测 3759 首的分布：二次元 1085、未标注 958、轻音乐 787、电子 468、原声 433、民谣 36、摇滚 15、古典 11。
想提高覆盖率就往 `RULES` 里加关键词，改完重跑 `classify`。

---

## 项目结构

```
src/netease_sorter/
├── api.py        # 接口封装（请求、重试、歌单读写）
├── browser.py    # 专用 Edge 窗口 + 调试端口取 Cookie
├── classify.py   # 语种 / 纯音乐判定，纯函数
├── genres.py     # 曲风多标签，规则表
├── pipeline.py   # 抓取 + 分类流水线，命令行和网页共用
├── target.py     # 歌单落点解析：名字 → id，重名/越权/非空的判断
├── export.py     # CSV 与 Console 脚本生成
├── store.py      # 本地文件读写
├── server.py     # 本地网页服务（标准库 http.server）
├── web/          # index.html / style.css / app.js，无框架无构建
└── cli.py        # 命令行
tests/
├── test_classify.py   # 10 个用例
├── test_genres.py     # 9 个用例
└── test_target.py     # 10 个用例
```

测试不需要 pytest：

```bash
python tests/test_classify.py
python tests/test_genres.py
python tests/test_target.py
```

---

## 常见问题

**扫码登录报 `code 8821`「请进行环境监测登录」**
网易云对部分账号的接口登录做了风控，旧扫码接口会被拦。用 `login --from-edge` 走浏览器登录，或者手工复制 `MUSIC_U`。

**能不能直接读浏览器里现成的 Cookie？**
读文件不行：Chrome / Edge 用 App-Bound Encryption，外部程序解不开；网易云 PC 客户端的 Cookie 也是 AES 加密、密钥不落盘。`--from-edge` 是**从浏览器进程内部**把 Cookie 取出来。

**为什么 `--from-edge` 要另开一个 Edge 窗口？**
默认配置目录上开不了调试端口（Chrome 136+），复制配置目录又会让 Cookie 失效。专用配置目录绕开这个限制，代价是第一次要单独登录一次。

**登录一次就够了吗**
够。Cookie 存在 `data/edge-profile/`，之后 `login --from-edge` 立刻返回；失效时会重新等你扫码。

**想换账号**
`login --from-edge --profile data/edge-profile-b`，或者删掉 `data/edge-profile/` 重新登录。切换后 `data/session.json` 会被覆盖。

**会被封号吗**
脚本只做「创建歌单 / 添加歌曲」这类正常操作，但短时间大量写入仍可能触发风控。默认每批 100 首、间隔 1.2 秒，失败会退避重试 3 次，仍然失败就**中止**而不是继续刷。别用别人的 Cookie，别开高并发。

**曲风为什么一堆「未标注」**
接口没有曲风字段，只能靠关键词猜；猜不出来就老实标「未标注」。想减少就补 `RULES`。

**网页里能加载「我喜欢的音乐」吗**
不能，网页走公开歌单接口。喜欢列表需要登录态，用命令行 `fetch --liked`。

**数据会传到网上吗**
不会。所有数据都在 `data/` 下，`.gitignore` 已排除；Cookie 只存在本地。

---

## 免责声明

仅供个人整理自己的歌单使用。接口是网页端的私有接口，随时可能变动或失效；请控制请求频率，不要用于批量抓取、商业用途或任何违反网易云服务条款的场景。使用风险自负。

## License

MIT
