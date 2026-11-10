# -*- coding: utf-8 -*-
"""命令行入口:ingest / query / eval / serve(设计 §11)。"""
from __future__ import annotations

import argparse
import json
import sys


def _add_config_arg(parser):
    parser.add_argument("--config", default=None, help="YAML 配置文件路径(可选)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="techdocs-rag", description="多技术栈技术文档 RAG 问答系统")
    sub = parser.add_subparsers(dest="cmd")

    p_ingest = sub.add_parser("ingest", help="从本地目录全量/增量同步文档")
    p_ingest.add_argument("--path", required=True, help="文档根目录")
    _add_config_arg(p_ingest)

    p_query = sub.add_parser("query", help="问答")
    p_query.add_argument("--q", required=True, help="问题")
    p_query.add_argument("--session", default=None, help="多轮会话 id")
    p_query.add_argument("--version", default=None, help="显式文档版本(如 1.28)")
    p_query.add_argument("--permission", action="append", default=["public"], help="权限域,可多次")
    p_query.add_argument("--json", action="store_true", help="输出 JSON")
    _add_config_arg(p_query)

    p_eval = sub.add_parser("eval", help="跑 golden set 评估")
    p_eval.add_argument("--golden", required=True, help="golden.jsonl 路径")
    p_eval.add_argument("--docs", default=None, help="评估前先入库的文档目录(可选)")
    _add_config_arg(p_eval)

    p_serve = sub.add_parser("serve", help="启动 HTTP API")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    _add_config_arg(p_serve)

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 1

    from techdocs_rag.bootstrap import build_context

    ctx = build_context(config_path=args.config)

    if args.cmd == "ingest":
        report = ctx.pipeline.sync(ctx.local_connector(args.path))
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 0 if report.failed == 0 else 2

    if args.cmd == "query":
        result = ctx.service.ask(
            args.q,
            session_id=args.session,
            permissions=set(args.permission),
            version=args.version,
        )
        if args.json:
            out = dict(result.__dict__)
            out["citations"] = [dict(c.__dict__) for c in result.citations]
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(result.answer)
            if result.citations:
                print("\n引用:")
                for c in result.citations:
                    mark = "✓" if c.valid else "✗"
                    print("  %s %s(%s)" % (mark, c.source_id, c.section or "-"))
            if result.refused:
                return 3
        return 0

    if args.cmd == "eval":
        if args.docs:
            report = ctx.pipeline.sync(ctx.local_connector(args.docs))
            print("入库: %s" % json.dumps(report.as_dict(), ensure_ascii=False))
        from techdocs_rag.evaluation.runner import EvalRunner

        report = EvalRunner(ctx.service).run(args.golden)
        summary = {k: v for k, v in report.items() if k != "per_query"}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "serve":
        import uvicorn

        from techdocs_rag.api.app import create_app

        app = create_app(qa_service=ctx.service, pipeline=ctx.pipeline, config=ctx.config)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
