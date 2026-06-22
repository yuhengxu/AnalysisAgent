"""FastAPI 应用入口。

职责：
- 初始化统一日志（最先执行）。
- 创建 FastAPI 实例、配置 CORS。
- 注册各业务路由（data / analytics / agent / reports / forecast / prediction）。
- 启动时建表并确保默认月报模板存在。
- 提供 ``/health`` 健康检查与请求耗时日志中间件。

模块调用关系详见 docs/03~10 各模块文档与 docs/09-数据流转与时序.md。
"""
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, analysis, analytics, auth, data, forecast, llm, llm_logs, prediction, reports
from app.core.config import settings
from app.core.database import SessionLocal, engine, init_db
from app.core.logging import get_logger, setup_logging
from app.core.migrate import run_migrations
from app.services.report import ReportService
from app.services.user_seed import ensure_default_admin

# 日志必须在任何业务模块产生日志前初始化
setup_logging(settings.logs_dir)
logger = get_logger("api")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """记录每个请求的方法、路径、状态码与耗时。"""
        start = time.time()
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(data.router, prefix=prefix)
    app.include_router(analysis.router, prefix=prefix)
    app.include_router(analytics.router, prefix=prefix)
    app.include_router(agent.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(forecast.router, prefix=prefix)
    app.include_router(prediction.router, prefix=prefix)
    app.include_router(llm_logs.router, prefix=prefix)
    app.include_router(llm.router, prefix=prefix)

    @app.on_event("startup")
    def startup():
        logger.info("应用启动：建表并确保默认月报模板存在")
        init_db()
        run_migrations(engine)
        db = SessionLocal()
        try:
            ensure_default_admin(db)
            ReportService(db).ensure_default_template()
        finally:
            db.close()
        logger.info("默认 LLM provider=%s", settings.default_llm_provider)

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
