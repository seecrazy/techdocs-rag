---
tech_stack: k8s
doc_type: guide
authority_level: authoritative
version: "1.29"
permission_scope: public
---
# Sidecar 容器(1.29 原生支持)

## 原生 sidecar
从 1.29 起,sidecar 容器正式 GA(new-sidecar-note)。在 initContainers 中声明 restartPolicy: Always 即可,Pod 启动时先启动 sidecar,应用容器退出后 sidecar 同步终止。

```yaml
initContainers:
- name: log-proxy
  image: log-proxy:1.4
  restartPolicy: Always
```

## 与旧方案对比
原生 sidecar 支持独立重启与 probes,不再需要 hack init 容器。
