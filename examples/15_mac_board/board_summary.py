"""演示：板块汇总（总成交金额、主力资金流向）。

通过 MacClient 的 get_board_summary() 获取板块聚合数据，包含成交额、
主力净流入、涨跌家数等。内部基于 get_board_members() 获取全部成分股后求和。

board_symbol: 板块代码字符串，如 "881001"（酒店餐饮）。
取自 BoardInfo.code 或 get_board_list()。

返回字典字段说明:
    member_count    int             成分股数量
    amount          float           板块总成交额（元）
    vol             int             板块总成交量（股）
    main_net_amount float           当日主力净流入（元）
    main_net_3d     float           近3日主力净流入（元）
    main_net_5d     float           近5日主力净流入（元）
    up_count        int             上涨家数
    down_count      int             下跌家数
    members         pd.DataFrame    成分股明细
"""

from easy_tdx import MacClient

with MacClient.from_best_host() as c:
    # 获取行业板块 881001（酒店餐饮）的汇总数据
    result = c.get_board_summary("881001")

    print("=== 板块汇总 ===")
    print(f"成分股数量:  {result['member_count']}")
    print(f"总成交额:    {result['amount']:,.0f} 元")
    print(f"总成交量:    {result['vol']:,} 股")
    print(f"主力净流入:  {result['main_net_amount']:,.0f} 元")
    print(f"近3日主力:   {result['main_net_3d']:,.0f} 元")
    print(f"近5日主力:   {result['main_net_5d']:,.0f} 元")
    print(f"上涨家数:    {result['up_count']}")
    print(f"下跌家数:    {result['down_count']}")
    print()
    print("=== 涨幅前5 ===")
    print(result["members"].head(5).to_string(index=False))

# 运行结果:
# === 板块汇总 ===
# 成分股数量:  35
# 总成交额:    5,823,456,000 元
# 总成交量:    412,356,789 股
# 主力净流入:  -123,456,000 元
# 近3日主力:   -345,678,000 元
# 近5日主力:   -234,567,000 元
# 上涨家数:    18
# 下跌家数:    17
#
# === 涨幅前5 ===
# market  code   name  pre_close  close   vol      amount  main_net_amount
#      1  603XXX  XX酒店    16.82  18.50  45200   80500000         1234567
#      0  000728  华天酒店    2.96   3.25 125600   39500000         -234567
#      0  002XXX  XX文旅    14.41  15.80  32100   49200000          345678
#      1  600XXX  XX餐饮    11.26  12.30  28900   34600000         -456789
#      0  000XXX  XX酒店     8.16   8.90  56700   49800000          567890
