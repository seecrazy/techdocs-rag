---
tech_stack: k8s
doc_type: guide
authority_level: authoritative
version: "1.28"
permission_scope: public
---
# Sidecar 容器(1.28 旧方案)

## init 容器模拟方案
在 k8s 1.28 中,原生 sidecar 尚未稳定(legacy-sidecar-note)。旧方案使用 init 容器加 restartPolicy: Always 模拟常驻 sidecar,缺点是无法独立重启、与主容器生命周期耦合。

## 已知限制
该方案已废弃(deprecated),升级到 1.29 后请使用原生 sidecar 容器。
