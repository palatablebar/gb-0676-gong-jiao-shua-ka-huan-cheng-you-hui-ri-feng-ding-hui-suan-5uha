REASONS={"BAD_COLUMNS":"列数不匹配","EMPTY_VALUE":"必填值为空","INVALID_NUMBER":"数字格式错误","INVALID_TIME":"时间缺少偏移或格式错误","DUPLICATE_CONFLICT":"同键取值冲突","UNKNOWN_REFERENCE":"引用不存在","STALE_VERSION":"版本已更新","EMPTY_FILE":"文件为空","HEADER_ONLY":"仅有表头","BLANK_ONLY":"全部为空行","UNKNOWN_ROUTE":"线路未登记","EMPTY_CARD":"卡号为空","FAILED_TAP":"失败刷卡不构成行程","SIMULTANEOUS_TAP":"同卡同刻多行程","NEGATIVE_FARE":"实扣金额不能为负","MISSING_FIELD":"缺少字段"}
TEXT_REASONS={"FORMULA_PREFIX":"公式样式文本：保留原值，发布时加单引号前缀呈现","CONTROL_PREFIX":"控制字符开头：保留原值，发布时加单引号前缀呈现"}
DISPOSITIONS={"accepted":"采纳","quarantine":"隔离","duplicate":"重复行","blank":"空白行","repeated_header":"分段表头","unplaced":"未着落"}
def reject(row, code, detail):
    return {**row,"reason":code,"detail":detail}
def sources(row):
    return row.get("_sources", [row.get("_line",0)])
