# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离、lineage（逐来源行处置台账）与line_metrics（未着落行、空缺段、是否完整）。/api/upload接收multipart文件file。

/api/runs/<id>/archive是唯一证据导出：每个来源行恰好一行，含原始行号与物理区间、处置结论、公式样式文本的原值（original_b64，`base64:` 前缀的JSON）与安全呈现值（rendered，单引号前缀）及完整记录JSON（evidence）。响应头 X-Archive-Version 与 X-Archive-SHA256 标识当前发布版本；同样内容重复获取不新增版本，构建或写入失败时保留上一版。

台账未逐行着落、批次缺少台账或行数未对平时，日结与导出分别以 LINEAGE_GAP / UNBALANCED 拒绝（409/422）。重跑同源同参数复用既有批次。
