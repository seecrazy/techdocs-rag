---
tech_stack: spring
doc_type: guide
authority_level: authoritative
version: "3.2"
permission_scope: public
---
# Spring Boot 应用部署

## 连接 Redis 超时配置
Spring Boot 应用连接 Redis 出现超时时,通过 spring.data.redis.timeout 控制命令超时,lettuce 连接超时单独配置:

```yaml
spring:
  data:
    redis:
      timeout: 3000ms
      lettuce:
        pool:
          max-active: 16
```

## 部署配置
Spring Boot 应用部署时建议:外部化配置(环境变量优先)、健康检查端点暴露给探针、优雅停机开启 server.shutdown: graceful。

## Bean 注册
使用 @Bean 在配置类注册组件,@Autowired 按类型注入;循环依赖优先通过 @Lazy 或结构调整解决。
