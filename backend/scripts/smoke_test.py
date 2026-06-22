import httpx

base = "http://127.0.0.1:8000/api/v1"
with httpx.Client(timeout=120) as c:
    print("health", c.get("http://127.0.0.1:8000/health").json())
    seed = c.post(f"{base}/data/seed").json()
    print("seed files", len(seed.get("results", [])))
    ds = c.get(f"{base}/data/datasets").json()
    print("datasets", len(ds), "total rows", sum(d.get("row_count", 0) for d in ds))
    dash = c.get(f"{base}/analytics/dashboard").json()
    print("dashboard symbols", list(dash.get("symbols", {}).keys())[:5])
    chart = c.get(f"{base}/analytics/charts/price_trend").json()
    print("chart series", len(chart.get("series", [])))
    agent = c.post(
        f"{base}/agent/run",
        json={"prompt": "分析Brent", "skill": "analyze", "model_provider": "mock"},
    ).json()
    print("agent tools", agent.get("tools_called"))
    fc = c.post(f"{base}/forecast/run", params={"symbol": "Brent"}).json()
    print("forecast scenarios", len(fc.get("scenarios", [])))
    rep = c.post(
        f"{base}/reports/generate",
        json={
            "issue_no": "2026年第6期（总57期）",
            "report_date": "2026年6月7日",
            "review_year": 2026,
            "review_month": 5,
            "outlook_year": 2026,
            "outlook_month": 6,
        },
    ).json()
    print("report", rep.get("title"), rep.get("docx_path"))
