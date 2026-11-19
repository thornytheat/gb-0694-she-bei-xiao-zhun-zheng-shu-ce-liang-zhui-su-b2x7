# 接口

`POST /api/run`：JSON中的csv文本，省略使用样例；或multipart字段file。最大5MB。

`POST /api/m1`至`POST /api/m8`：独立运行到指定模块，JSON结构同运行接口。M8返回`declarations`（结构化声明，含来源证书、合成标准不确定度u_c、扩展不确定度U、声明区间、允许偏差、缺失证书与线性累加基线）与页面证据行。

`GET /api/history`：历史批次。`POST /api/review`接收id、revision和decision（通过或退回）。`GET /api/evidence.csv`提供单一证据导出。

`GET /api/declarations`：声明登记表，可选查询参数`run_id`与`status`（有效/已重算）。声明编号确定性生成：同批重跑不新增登记；上游更新后旧声明置“已重算”并以`superseded_by`指向新声明。

结构错误422，版本变化409，文件过大413；错误返回code与message。所有页面可从左侧八个模块入口访问。

`GET /api/runs/<id>`读取指定批次；页面与证据CSV通过run_id查询参数绑定批次，模块导航保留该参数。

JSON请求体必须是对象，数组、标量、null、损坏JSON及错误上传字段返回400，且不运行默认样例。
