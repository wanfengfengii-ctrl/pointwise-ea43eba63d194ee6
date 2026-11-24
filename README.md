# 澄岚涂层试验室换档核定

白班以实际工艺顺序登记换档试验，冻结两台测厚仪的分段实读，预检后发行。夜班在独立中心库实收，关掉台架源库后核定共同换档。主管可以在勘误后按原号领取当时的签报和回执。

## 运行

使用 Python 3.11 标准库。从项目根目录运行 `python3 -B check_project.py` 执行完整回归。控制台物化时提供这个入口。也可以直接运行 `python3 -B -m unittest discover -s tests -t . -v` 发现全部原测试。

运行 `python3 -B demo.py` 在独立临时 SQLite 库里执行两个固定样例。原签的总残差为 8 μm，三个段界各有闭区间 [−2,2] μm。勘误后的签报残差为零，只有第二个段界和跳变量 2 μm。演示重新打开中心库读取这两份定稿，打印实际预检、精确结论、父件的实收号、台架与修订号以及回执。

## Python 入口

使用 `lab.open_source(path)` 与 `lab.open_center(path)` 打开不同的 SQLite 库，由调用者负责关闭。初始化可重复且保留已有数据。接口拥有各自的写事务，请在事务外调用。下例从项目根目录运行，库文件路径由调用者选择。

```python
from contextlib import closing
from lab import open_source, open_center
from trial.catalog import define_trial
from bench.revisions import record_revision
from bench.precheck import precheck
from evidence.issue import issue
from evidence.intake import receive
from analysis.request import publish
from report.history import read
from report.export import export_report

with closing(open_center('center.sqlite')) as center:
    with closing(open_source('source.sqlite')) as source:
        for database in (source, center):
            define_trial(database, '试验1', ['预热', '稳态'], ['甲', '乙'])
        a = record_revision(source, '试验1', '甲', [('预热', 0), ('稳态', '3/2')])
        b = record_revision(source, '试验1', '乙', [('预热', 100), ('稳态', '203/2')])
        checks = precheck(source, a.revision_id)
        first = receive(center, '试验1', issue(source, a.revision_id).to_json())
        second = receive(center, '试验1', issue(source, b.revision_id))
    signed = publish(center, '试验1', first.received_id, second.received_id)
    historical = read(center, signed.snapshot.report_id)
    exported = export_report(center, historical.snapshot.report_id)
```

清单单位使用 `um`。段序至少含一段，段名唯一，角色是两个彼此不同的非空名字。相同定义可重登。试验标识已存在且内容不同时拒绝。修订接受 `(段名, 读数)` 行或 `bench.readings.Reading`。读数接受整数、精确字符串或 `Fraction`，`None` 表示明确缺测。浮点数和布尔值会被拒绝。零及重复实读照常计入。一段内行序保留，段界依清单顺序生成。勘误用 `parent_revision_id=` 指定同试验同角色的父号并提交完整快照，旧修订仍可预检或发行。

`issue` 返回不可变 V1 站件。`.to_json()` 生成规范传输文本，`receive` 同时接受站件对象。发行标识是独立的透明度无关标识，具体值仅用于来源核对。摘要绑定发行标识、修订、角色、完整清单标识与正文，供中心检查传输一致性。中心信任业务授权渠道交付的站件。一次成功实收有自己的中心实收号。正文按段界位置存放资格和条件残差的精确分段响应。原读行、绝对读数及零位保存在源库。

预检分别拟合本站界两侧的中位数。联合核定对同一候选段界及有符号跳变量 `d`，从每站后侧读数减去 `d`，分别在本站调整后读数上取中位数，再相加两站绝对残差。两站都在界的两侧有实读才纳入计算。签报记录全部全局并列的段界、闭区间及按请求顺序的父件。单点以相同端点表示。`no_common_evidence` 是可签的缺证状态，最小值为 `None`，区间列表为空。数据库及导出的精确数值使用规范分数字符串。

参数、清单冲突、选件或站件校验失败产生 `ValueError`。合法格式的未知记录号产生 `LookupError`。数据库写入或提交错误由 `sqlite3.Error` 报告，失败操作整次回滚。原签定稿、父件和成功回执一同提交，可按报告号读取或导出。历史读取使用持久快照。

## 定向复测工单

夜班可凭旧签报办理定向复测。台架在关库前按旧报告父件中的 `origin.issue_id` 用 `evidence.issue.issue_supplement` 出补件，补件绑定原发行件及其修订、角色、清单和本站条款，绝对读数与台架零位留站。中心凭 V1 实收号用 `evidence.intake.receive_supplement` 核对实收，断源后用 `analysis.request.publish_review` 仅在旧签报的最优段界和跳变量范围内复核：两台共用一个跳变量，同台条款共用一个使本站绝对残差最小的基值，逐条要求指定段的有效实读严格超过所指方向的容限。签出的精确可行区间、端点开闭和各条款出处按 `report.history.read_review` 以新号领取，定稿与回执一同保存。详见 RETEST.md。
