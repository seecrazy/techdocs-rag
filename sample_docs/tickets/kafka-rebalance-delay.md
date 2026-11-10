---
tech_stack: kafka
doc_type: troubleshooting
authority_level: operational
permission_scope: internal
---
# 工单:消费延迟

## 问题
消费者组的 consumer group 频繁 rebalance,消费延迟持续上涨,报警触发。

## 解决
定位到消费者处理慢导致 session 超时:调大 session.timeout.ms 到 60000、heartbeat.interval.ms 到 6000,并将 max.poll.records 调小到 200,重平衡消失,延迟回落。

## 复盘
处理耗时接近 max.poll.interval.ms 时优先扩分区/加消费者,而不是一味调大超时。
