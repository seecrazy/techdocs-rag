# 技术文档 RAG 实现计划

> **执行方式**:本会话原生执行(用户已明确指示"开始开发")。规格 = `docs/DESIGN.md`(v2.0),执行时同读。
> **验证命令**:`.venv/bin/pytest`(全量绿才算完成);TDD:每模块先写测试、看失败、再实现。

**Goal**:交付可运行的多技术栈文档 RAG v0.1——入库(结构切分/元数据校验/删除传播)→ 检索(路由/改写/混合/过滤/重排/拒答)→ 生成(溯源/引用校验)→ 评估/Trace/API/CLI。

**Architecture**:六层流水线;存储统一抽象(SQLite chunk store + 内存向量/BM25 索引,重启重建);embedding/LLM/重排全部可插拔,默认零外部依赖(哈希 embedding、Mock/OpenAI 兼容客户端),环境变量切换真实服务。

**Tech Stack**:Python 3.9+(stdlib sqlite3/json/urllib),pyyaml、fastapi、uvicorn;pytest。

## Global Constraints

- Python 3.9 兼容:所有模块 `from __future__ import annotations`;禁用 `match`、`tomllib`、运行时 `X | Y`。
- 核心零重依赖:chromadb / sentence-transformers 只允许惰性导入(prod extra)。
- 元数据必填字段缺失/非法 → 拒绝入库(设计 §2.3),不得静默填默认。
- 版本比较用数值元组,禁止字符串比较(设计 §6.5)。
- 权限过滤必须发生在检索通道内部(设计 §6.6),禁止生成端后置过滤。

## Review Focus(易咬人的输入与期望行为)

1. 短追问"它的默认值?"带会话历史 → 必须改写为独立查询再检索(§5.1)。
2. 中文提问命中英文术语文档 → 术语扩展后 BM25 必须召回(§5.2)。
3. 显式版本"1.28" → superseded 旧版可见;未指定 → 旧版被过滤(§6.5)。
4. 编造引用 `[来源: ghost.md]` → 运行期移除 + 警告(§7.3)。
5. external + injection_suspect → 永不进入 Prompt(§8.1)。
   对应测试分别钉在 test_rewriter / test_hybrid / test_hybrid / test_citation / test_injection + test_query_flow。

## 文件结构与接口契约

```
src/techdocs_rag/
  text.py          # tokenize(text)->list[str](ASCII整词+子词+CJK bigram); approx_tokens(text)->int
  models.py        # ChunkMetadata.validate()->None(raise MetadataError); Chunk.make_id(); RetrievedChunk; Citation; AnswerResult; SyncReport; 权重常量 AUTHORITY_WEIGHT
  config.py        # AppConfig(data_dir,traces_dir,chunking,retrieval,refusal,security); load_config(path|None)
  connectors/base.py     # BaseSourceConnector: discover/fetch/get_incremental_cursor/map_metadata
  connectors/local_file.py # LocalFileConnector(root, rules:list[(prefix,overrides)], front-matter 优先于 rules)
  ingestion/parser.py    # Block(type,text,level,lang); split_front_matter(text)->(dict|None,body); MarkdownParser.parse(text)->list[Block]
  ingestion/chunker.py   # StructureAwareChunker(chunking_cfg).chunk(blocks, meta)->list[Chunk](父子块, is_parent 不入索引)
  security/injection.py  # scan(text)->bool; SUSPECT_PATTERNS
  storage/chunkstore.py  # SQLiteChunkStore: upsert_many/get/ get_many/ delete_by_source/ children(collection)/ parents(collection,ids)/ all_chunks(collection)
  storage/indexstore.py  # IndexStore: upsert_chunks(父不入索引)/delete_by_source/vector_search(collection,vec,k,pred)->[(id,cos)]/bm25_search(collection,query_text,k,pred)->[(id,score)]/hybrid_search(见下)/rebuild()
  ingestion/pipeline.py  # IngestionPipeline.sync(connector)->SyncReport(验收①②③)
  embeddings.py    # Embedder(ABC); HashEmbedder(dim=512); OpenAICompatibleEmbedder; build_embedder(env)
  generation/llm.py      # LLMClient(ABC).chat(system,messages)->str; OpenAICompatibleLLMClient(urllib); MockLLM(handler)
  retrieval/router.py    # RoutingResult(stacks,method,confidence,version,doc_type_hint); route(query, llm=None)
  retrieval/rewriter.py  # QueryRewriter.rewrite(query, history)->RewrittenQuery(text, expansions)
  retrieval/filters.py   # RetrievalFilters(permissions,version,include_superseded); build_filter(f, family_latest)->pred
  retrieval/reranker.py  # Reranker(ABC); NoopReranker; LLMReranker; CrossEncoderReranker(惰性)
  retrieval/hybrid.py    # hybrid_search(store, collection, query_text, vec, filters, cfg)->list[RetrievedChunk](RRF×authority, relevance=max(cos,sat(bm25)))
  generation/prompt.py   # SYSTEM_PROMPT; assemble_context(chunks, max_tokens)->str
  generation/citation.py # extract_citations(answer)->list[Citation]; validate_and_clean(answer, allowed_ids)->(clean, citations, n_invalid)
  generation/service.py  # QAService.ask(question, session_id, permissions, version)->AnswerResult(改写→路由→混合→重排→拒答→父扩展→组装→LLM→引用校验)
  observability/trace.py # TraceStore.append(record); update_feedback(trace_id, helpful)
  evaluation/metrics.py  # context_recall/ context_precision/ routing_accuracy/ suggest_threshold
  evaluation/runner.py   # EvalRunner.run(golden_path)->report(dict)
  bootstrap.py     # build_context(config_path, env)->Context(config, store, docstore, embedder, llm, ...)
  api/app.py       # create_app()→FastAPI(POST /api/query,/api/ingest,/api/feedback; GET /api/health)
  cli.py           # ingest/query/eval/serve 子命令
```

## 任务(每任务=测试文件+实现,RED→GREEN)

1. 基础件:`text.py` + `models.py` + `config.py` — tests/test_text_models.py(tokenize 不切碎 E1024/spring.redis.timeout、CJK bigram;元数据缺失拒收;权重常量)
2. 解析切分:parser + chunker — test_parser_chunker.py(标题路径、代码块原子、表格原子、父子块、重叠、deprecated 标记)
3. 注入扫描:injection.py — test_injection.py(中英模式、干净文本不误报)
4. 存储:indexstore(+SQLite) — test_indexstore.py(持久化重建、按 source_id 删除、向量/BM25 检索 + 谓词过滤)
5. 接入管线:pipeline + local_file 连接器 — test_ingestion.py(验收①②③、元数据拒收、family_key、注入标记、quarantine)
6. 路由与改写:router + rewriter — test_router.py(各栈规则、多栈、版本提取、LLM 兜底)、test_rewriter.py(指代改写、双语扩展)
7. 检索与过滤:filters + hybrid — test_hybrid.py(RRF×authority 次序、权限谓词、latest/superseded、显式版本穿透、relevance 信号)
8. 生成:prompt + citation + service(+MockLLM) — test_citation.py(合法保留/编造移除)、test_query_flow.py(端到端:溯源、拒答在 LLM 前、多轮、多栈归因、注入排除)
9. 观测评估:trace + metrics + runner — test_metrics.py(数值正确性、阈值建议)
10. API + CLI + bootstrap — test_api.py(health/query e2e)
11. 冒烟:sample_docs 入库 + 演示查询;README。

提交节奏:每任务绿即 `git commit`。
