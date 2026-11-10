---
tech_stack: database
doc_type: troubleshooting
authority_level: authoritative
version: "8.0"
permission_scope: internal
---
# MySQL 死锁排查

## 查看死锁信息
执行以下命令查看最近一次死锁的详细信息:

```sql
SHOW ENGINE INNODB STATUS;
```

LATEST DETECTED DEADLOCK 段包含两个事务持有的锁与等待的锁。

## 常见成因与处理
- 事务内多条 UPDATE 顺序不一致:统一按主键顺序更新
- 大事务持锁过久:拆小事务,避免在事务中做外部调用
- 二级索引加锁范围扩大:检查执行计划,必要时强制主键访问

出现死锁后 MySQL 会自动回滚代价较小的事务,应用侧应捕获 1213 错误码并重试。
