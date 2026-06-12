# Welcome to easy-tdx Discussions!

## 👋 欢迎！

感谢你来到 easy-tdx 社区！

这个项目的初心很简单：**打破金融数据的获取门槛，让每个人都能拿到和机构一样的行情数据。** 免费、开源、无需注册、无需 API Key。

不管你是量化新手还是老手，这里就是我们的交流阵地。

## 💬 在这里你可以

- **提问** — 安装报错、API 用法、数据字段含义……任何问题都可以问，没有"太基础"这回事
- **分享策略** — 写了不错的回测策略？发现了好用的指标组合？发出来大家一起看看
- **反馈 Bug** — 命令跑不通、数据不对劲、接口返回异常，直接贴出来
- **提 Feature** — 觉得缺了什么功能？说出来，社区一起评估优先级
- **晒成果** — 用 easy-tdx 做了什么有意思的东西？数据分析、可视化、自动化交易面板……都欢迎展示

## 🚀 快速上手

还没装过的朋友，一行命令搞定：

```bash
pip install easy-tdx
```

然后试试：

```bash
easy-tdx kline SZ 000001 --count 30 --table
easy-tdx indicator MACD -m SH -c 600519 --table
easy-tdx serve  # 启动 Web API，浏览器打开 http://localhost:8000/docs
```

📖 完整文档看 [README](https://github.com/handsomejustin/easy_tdx) 和 [Wiki](https://github.com/handsomejustin/easy_tdx/wiki)。

## 🤝 社区共识

- 互相尊重，友善讨论
- 提问时尽量附上：版本号、命令/代码、报错信息
- 答疑是社区互助，没有义务回复，但每一条都会有人看到
- **不构成投资建议** — 本工具仅供学习研究，投资决策风险自担

---

**现在就从下面留个言开始吧** 🎉 告诉我们你用 easy-tdx 在做什么，或者打算拿它做什么。
