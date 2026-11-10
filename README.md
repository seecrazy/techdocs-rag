# techdocs-rag

多技术栈(K8s / Kafka / Redis / Spring / 数据库)技术文档 RAG 问答系统。

**结构化切分 · 混合检索(BM25+向量+RRF) · 强制溯源与引用运行期校验 · 多技术栈路由隔离 · 多轮改写 · 权限/版本过滤 · Prompt 注入防护 · 拒答校准 · 全链路 Trace · golden 评估**

完整设计见 **[docs/DESIGN.md](docs/DESIGN.md)**(v2.0),实现计划见 [docs/plans/2026-11-10-techdocs-rag.md](docs/plans/2026-11-10-techdocs-rag.md)。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 1. 入库样例文档(增量幂等,源端删除自动传播)
.venv/bin/techdocs-rag ingest --path sample_docs

# 2. 问答(默认离线 Mock LLM + 哈希 embedding,零外部依赖)
.venv/bin/techdocs-rag query --q "kafka consumer group rebalance 触发条件" --permission public --permission internal

# 3. 多轮会话 + 显式版本
.venv/bin/techdocs-rag query --q "Kafka 消费者组 session.timeout.ms 是什么" --session s1 --permission public
.venv/bin/techdocs-rag query --q "那它的默认值是多少?" --session s1 --permission public
.venv/bin/techdocs-rag query --q "k8s 1.28 sidecar 怎么用" --permission public

# 4. golden 评估(输出 Recall / 路由准确率 / 引用准确率 / 建议拒答阈值)
.venv/bin/techdocs-rag eval --golden eval/golden.jsonl

# 5. HTTP API
.venv/bin/techdocs-rag serve --port 8000
#   POST /api/query     {"question": "...", "permissions": ["public","internal"], "session_id": "s1"}
#   POST /api/ingest    {"path": "sample_docs"}
#   POST /api/feedback  {"trace_id": "...", "helpful": false, "comment": "..."}
#   GET  /api/health | /api/stats

# 6. 测试
.venv/bin/pytest
```

## 接入真实模型(可选)

默认零依赖离线运行。设置环境变量即切换到任意 OpenAI 兼容服务(示例为火山方舟):

```bash
export TECHDOCS_LLM_API_BASE="https://ark.cn-beijing.volces.com/api/v3"
export TECHDOCS_LLM_API_KEY="<ARK API KEY>"
export TECHDOCS_LLM_MODEL="<接入点/模型 ID>"

# 多语 embedding(英文文档 + 中文提问场景必须用多语模型,设计 §6.3)
export TECHDOCS_EMBEDDING_API_BASE="https://ark.cn-beijing.volces.com/api/v3"
export TECHDOCS_EMBEDDING_API_KEY="<ARK API KEY>"
export TECHDOCS_EMBEDDING_MODEL="bge-m3(或对应接入点)"

# 重排: noop(默认) | llm(用上面 LLM 打分) | cross_encoder(需 pip install ".[prod]")
export TECHDOCS_RERANKER=llm
```

切换 embedding 模型后需全量重建索引(删除 `.techdocs_data/` 重新 ingest,设计 §4.4)。

## 文档元数据

每个文档通过 YAML front-matter 声明元数据(必填字段缺失会被拒收,设计 §2.3)。**version 必须加引号**,避免 YAML 浮点陷阱:

```yaml
---
tech_stack: kafka            # k8s|kafka|redis|spring|database|cross|unknown
doc_type: guide              # api_reference|guide|troubleshooting|changelog|code_example|table|other
authority_level: authoritative  # authoritative|operational|external
version: "3.6"               # 引号!
permission_scope: public     # public|internal|restricted:<group>
---
```

路径中的 `v1.28/` 目录会被识别为版本目录,同族文档默认只检索最新版本(设计 §6.5)。

## 生产适配

- **向量库**:实现 `IndexStore` 同名接口(`upsert_chunks/delete_by_source/vector_search/bm25_search`)即可替换为 Qdrant / Milvus / Chroma / ES(当前为 SQLite 持久化 + 内存索引,<10 万 chunk 开发规模)。
- **连接器**:继承 `BaseSourceConnector` 实现 `discover/fetch/get_incremental_cursor/map_metadata` 四个方法(Git/Confluence/工单/Web 按设计 §2.2 排期)。
- **权限**:生产环境由网关注入会话权限,勿信任客户端 `permissions` 字段(设计 §8.2)。

## 项目结构

```
docs/DESIGN.md          完整设计 v2.0(含 v1.0→v2.0 变更记录)
src/techdocs_rag/
  text.py models.py config.py          分词/模型/配置
  connectors/                           连接器抽象 + 本地文件
  ingestion/                            解析、结构感知切分、接入管线
  storage/                              SQLite chunk store + 内存向量/BM25 + DocStore
  retrieval/                            路由/改写/过滤/混合检索/重排
  generation/                           Prompt/引用校验/QAService/LLM 客户端
  security/                             Prompt 注入扫描
  evaluation/ observability/            指标/golden runner/Trace
  api/ cli.py bootstrap.py              FastAPI/命令行/装配
sample_docs/                            样例知识库(含工单、外部注入样例、版本化文档)
eval/golden.jsonl                       golden 评估集
```

## 路线图

查询/语义缓存、summary chunk(概览类查询)、结构化参数通道、多跳检索(设计 §10)。
