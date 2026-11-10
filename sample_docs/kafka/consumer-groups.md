---
tech_stack: kafka
doc_type: guide
authority_level: authoritative
version: "3.6"
permission_scope: public
---
# Kafka 消费者组与重平衡

## 消费者组机制
消费者组(consumer group)由多个消费者实例组成,共同订阅一组 topic。一个 partition 在同一时刻只能被组内的一个消费者消费,消费者组通过 partition 分配实现水平扩展与容错。

## 重平衡触发条件
以下三类事件会触发 rebalance:

- 成员变化:消费者加入或退出消费者组
- 订阅变化:消费者订阅的 topic 或 partition 数量变化
- 超时:消费者未在 session.timeout.ms 内完成心跳,被判定离组(默认 45000ms)

## 避免重平衡的配置
使用静态成员与协作式分配策略可显著减少重平衡:

```properties
session.timeout.ms=45000
heartbeat.interval.ms=3000
partition.assignment.strategy=cooperative-sticky
group.instance.id=consumer-1
```

## 关键参数表
| 参数 | 默认值 | 说明 |
|---|---|---|
| session.timeout.ms | 45000 | 组会话超时,超时未心跳则触发重平衡 |
| heartbeat.interval.ms | 3000 | 心跳间隔,建议不超过 session.timeout.ms 的 1/3 |
| max.poll.interval.ms | 300000 | 两次 poll 最大间隔,超时消费者主动离组 |
