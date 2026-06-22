"""Direct service smoke test without HTTP."""
from pathlib import Path

from app.core.database import SessionLocal, init_db
from app.services.agent import AgentService
from app.services.analytics import AnalyticsService
from app.services.data_import import DataImportService
from app.services.forecast import ForecastService
from app.services.report import ReportService


def main():
    init_db()
    db = SessionLocal()
    try:
        importer = DataImportService(db)
        sample_dir = Path(__file__).resolve().parents[2] / "yuebao"
        results = importer.seed_sample_data(sample_dir)
        print("seed files", len(results))

        analytics = AnalyticsService(db)
        dash = analytics.dashboard_summary()
        print("dashboard symbols", list(dash.get("symbols", {}).keys())[:5])
        chart = analytics.chart_config("price_trend")
        print("chart series", len(chart.get("series", [])))

        forecast = ForecastService(db).run_forecast("Brent")
        print("forecast scenarios", len(forecast.get("scenarios", [])))

        report = ReportService(db).generate_monthly_draft(
            issue_no="2026年第6期（总57期）",
            report_date="2026年6月7日",
            review_month=(2026, 5),
            outlook_month=(2026, 6),
        )
        print("report", report.get("title"), report.get("docx_path"))

        agent = AgentService(db).run("分析Brent", skill="analyze")
        print("agent tools", agent.get("tools_called"))
        print("ALL TESTS PASSED")
    finally:
        db.close()


if __name__ == "__main__":
    main()
