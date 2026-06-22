import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.timezone import format_beijing_iso
from app.schemas.common import DataQueryParams
from app.services.data_export import DataExportService
from app.services.data_import import DataImportService
from app.services.data_query import DataQueryService
from app.services.agency_forecast import AgencyForecastService
from app.services.report_table_data import ReportTableDataService, ReviewPeriodMismatch, web_fetch_options

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(get_current_user)])


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    from app.models.dataset import Dataset

    rows = db.query(Dataset).order_by(Dataset.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "source_type": r.source_type,
            "row_count": r.row_count,
            "status": r.status,
            "created_at": format_beijing_iso(r.created_at),
        }
        for r in rows
    ]


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    service = DataImportService(db)
    content = await file.read()
    saved = service.save_upload(file.filename, content)
    try:
        result = service.import_file(saved, category)
    except ValueError as exc:
        try:
            detail = json.loads(str(exc))
        except json.JSONDecodeError:
            detail = {"message": str(exc)}
        raise HTTPException(status_code=400, detail=detail) from exc
    quality = service.quality_check(result["dataset_id"])
    table_sync = ReportTableDataService(db).sync_derived_after_import(
        result.get("category", category or ""),
        result,
        user=user,
    )
    return {"import": result, "quality": quality, "table_sync": table_sync}


@router.get("/catalog")
def data_catalog(db: Session = Depends(get_db)):
    return DataQueryService(db).catalog()


@router.post("/query")
def data_query(params: DataQueryParams, db: Session = Depends(get_db)):
    svc = DataQueryService(db)
    return {"data": svc.query(params), "charts": svc.charts_for(params)}


@router.post("/query/export")
def export_data_query(params: DataQueryParams, db: Session = Depends(get_db)):
    """导出当前查询条件对应的数据表与图表（Excel）。"""
    path = DataExportService(db).export_query_xlsx(params)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/seed")
def seed_sample(db: Session = Depends(get_db)):
    from pathlib import Path

    service = DataImportService(db)
    sample_dir = Path("/app/yuebao") if Path("/app/yuebao").exists() else Path("../yuebao")
    if not sample_dir.exists():
        sample_dir = Path(__file__).resolve().parents[3] / "yuebao"
    results = service.seed_sample_data(sample_dir)
    table_svc = ReportTableDataService(db)
    table_syncs: list[dict] = []
    for item in results:
        if item.get("error") or not item.get("category"):
            continue
        sync = table_svc.sync_derived_after_import(item["category"], item)
        if sync.get("periods"):
            table_syncs.append({"category": item["category"], **sync})
    return {"results": results, "table_syncs": table_syncs}


@router.get("/quality/{dataset_id}")
def quality_check(dataset_id: int, db: Session = Depends(get_db)):
    return DataImportService(db).quality_check(dataset_id)


@router.delete("/clear")
def clear_data(
    category: str | None = Query(None, description="price | balance | factor，为空则清空全部"),
    db: Session = Depends(get_db),
):
    if category and category not in {"price", "balance", "factor", "generic"}:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="category 须为 price、balance、factor 或留空")
    counts = DataImportService(db).clear_data(category)
    return {
        "status": "cleared",
        "category": category or "all",
        "counts": counts,
    }


@router.get("/agency-forecasts/schema")
def agency_forecast_schema():
    from app.templates.monthly_report import DEFAULT_TABLES

    tbl = DEFAULT_TABLES["table_agency"]
    return {
        "title": tbl["title"],
        "source": tbl["source"],
        "headers": tbl["headers"],
        "default_rows": AgencyForecastService.default_rows(),
    }


@router.get("/agency-forecasts")
def get_agency_forecast(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    svc = AgencyForecastService(db)
    entry = svc.get(year, month)
    if not entry:
        return {
            "year": year,
            "month": month,
            "rows": svc.default_rows(),
            "exists": False,
        }
    return {**entry, "exists": True}


@router.get("/agency-forecasts/list")
def list_agency_forecasts(db: Session = Depends(get_db)):
    return AgencyForecastService(db).list_all()


@router.put("/agency-forecasts")
def upsert_agency_forecast(
    body: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    year = int(body.get("year", 0))
    month = int(body.get("month", 0))
    rows = body.get("rows")
    if not year or not month or month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="year/month 无效")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows 须为二维数组")
    return AgencyForecastService(db).upsert(year, month, rows, user)


@router.get("/report-tables/schema")
def report_tables_schema():
    return {
        "tables": ReportTableDataService.table_schema(),
        "web_fetch": web_fetch_options(),
    }


@router.get("/report-tables/list")
def report_tables_list(db: Session = Depends(get_db)):
    return ReportTableDataService(db).list_periods()


@router.get("/report-tables")
def report_tables_get(
    review_year: int = Query(...),
    review_month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    return ReportTableDataService(db).list_tables(review_year, review_month)


@router.post("/report-tables/sync-derived")
def report_tables_sync_derived(
    body: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    ry = int(body.get("review_year", 0))
    rm = int(body.get("review_month", 0))
    if not ry or not rm or rm < 1 or rm > 12:
        raise HTTPException(status_code=400, detail="review_year/review_month 无效")
    oy = body.get("outlook_year")
    om = body.get("outlook_month")
    table_keys = body.get("table_keys")
    try:
        return ReportTableDataService(db).sync_derived(
            ry, rm,
            int(oy) if oy else None,
            int(om) if om else None,
            table_keys=table_keys if isinstance(table_keys, list) else None,
            user=user,
        )
    except ReviewPeriodMismatch as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/report-tables/fetch-web")
def report_tables_fetch_web(
    body: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    ry = int(body.get("review_year", 0))
    rm = int(body.get("review_month", 0))
    if not ry or not rm or rm < 1 or rm > 12:
        raise HTTPException(status_code=400, detail="review_year/review_month 无效")
    table_keys = body.get("table_keys")
    oy = body.get("outlook_year")
    om = body.get("outlook_month")
    enable_gdp = body.get("enable_gdp_llm_predict")
    try:
        return ReportTableDataService(db).fetch_web(
            ry, rm,
            outlook_year=int(oy) if oy else None,
            outlook_month=int(om) if om else None,
            table_keys=table_keys if isinstance(table_keys, list) else None,
            enable_gdp_llm_predict=bool(enable_gdp) if enable_gdp is not None else None,
            user=user,
        )
    except ReviewPeriodMismatch as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/report-tables/{table_key}")
def report_tables_upsert(
    table_key: str,
    body: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    ry = int(body.get("review_year", 0))
    rm = int(body.get("review_month", 0))
    rows = body.get("rows")
    if not ry or not rm or rm < 1 or rm > 12:
        raise HTTPException(status_code=400, detail="review_year/review_month 无效")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows 须为二维数组")
    try:
        return ReportTableDataService(db).upsert_manual(ry, rm, table_key, rows, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
