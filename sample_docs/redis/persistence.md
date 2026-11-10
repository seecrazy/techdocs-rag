---
tech_stack: redis
doc_type: guide
authority_level: authoritative
version: "7.2"
permission_scope: public
---
# Redis 持久化

## RDB 快照
RDB 以二进制快照方式持久化整个数据集,通过 save 配置或 bgsave 触发。优点是文件紧凑、恢复快;缺点是两次快照之间的数据会丢失。

## AOF 追加日志
AOF 记录每条写命令,appendfsync 控制刷盘频率(everysec 为默认折中)。数据安全性优于 RDB,文件更大,重写(rewrite)可压缩。

## 生产建议
同时开启 RDB 与 AOF:RDB 用于快速恢复与备份,AOF 用于降低数据丢失窗口。重启时 Redis 优先使用 AOF 恢复。
