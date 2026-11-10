---
tech_stack: k8s
doc_type: guide
authority_level: authoritative
version: "1.29"
permission_scope: public
---
# Pod 生命周期与排障

## 排查 CrashLoopBackOff
CrashLoopBackOff 表示容器反复崩溃。排查步骤:

1. `kubectl describe pod <name>` 查看 Events 中的退出码与原因
2. `kubectl logs <name> --previous` 查看上一次崩溃的日志
3. 检查探针配置与启动命令参数

常见原因:应用启动即退出(配置缺失)、liveness probe 过于激进、镜像入口命令错误。

## 探针配置示例
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Pod 阶段
Pending、Running、Succeeded、Failed、Unknown。Pending 卡住通常意味着调度失败(资源不足)或镜像拉取失败(ImagePullBackOff)。
