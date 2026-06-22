from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Energy Analysis Agent Platform"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./db/energy_platform.db"
    data_dir: Path = Path("./data")
    raw_dir: Path = Path("./data/raw")
    processed_dir: Path = Path("./data/processed")
    exports_dir: Path = Path("./data/exports")
    charts_dir: Path = Path("./data/charts")
    logs_dir: Path = Path("./logs")
    default_llm_provider: str = "volcengine"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    # DeepSeek 深度研究模式下的思考强度（high/max），普通模式不开启思考
    deepseek_reasoning_effort: str = "high"
    volcengine_api_key: str = ""
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_model: str = "doubao-seed-2-0-pro-260215"
    # 火山方舟可选模型目录覆盖/追加（JSON 数组，见 .env.example）
    volcengine_model_catalog: str = ""
    # 豆包深度研究模式：DeepSearch 智能体应用 ID（bot-xxx，方舟「应用广场」创建）
    # 集成浏览器使用、联网搜索、知识库、网页解析、ChatPPT、Python 代码执行器等 MCP 服务
    volcengine_deepsearch_bot_id: str = ""
    llm_timeout: int = 600
    # 深度研究模式（深度思考 / DeepSearch）单次调用允许更长耗时
    llm_deep_timeout: int = 900
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    admin_username: str = "admin"
    admin_password: str = "admin123"
    # 月报图表渲染引擎：matplotlib | echarts
    chart_renderer: str = "matplotlib"
    chart_echarts_fallback: bool = False
    chart_echarts_width: int = 1400
    chart_echarts_height: int = 780
    chart_echarts_device_scale: int = 3
    playwright_browser: str = "chromium"
    # 表2-2 GDP 增速：是否允许「深度研究联网获取」时调用大模型预测（默认关，手工填写）
    report_table_gdp_llm_predict: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"  # 兼容历史 .env 中已废弃的变量（如 WEB_SEARCH_*）


settings = Settings()

for path in [
    settings.data_dir,
    settings.raw_dir,
    settings.processed_dir,
    settings.exports_dir,
    settings.charts_dir,
    settings.logs_dir,
    Path("./db"),
]:
    path.mkdir(parents=True, exist_ok=True)
