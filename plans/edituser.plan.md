# AnalysisAgent 用户管理、页面权限、月报隔离与并发支持修改方案

## 1. 任务背景

当前项目已经具备基础登录体系，包括：

- 后端 `/auth/login` 登录接口
- JWT token 生成与校验
- `users` 表
- 默认管理员种子逻辑
- `get_current_user`
- `require_admin`
- 前端 `ProtectedRoute`
- 前端 `AdminRoute`
- 前端 `AuthContext`

因此，本次需求不建议重写认证系统，而应在现有认证体系上扩展用户管理、页面权限、月报隔离和并发能力。

---

## 2. 总体目标

新增一个“用户管理”模块，满足以下要求：

1. 管理员用户可以新增普通用户。
2. 管理员用户可以删除普通用户。
3. 新增普通用户的初始密码固定为 `qwer1234`。
4. 管理员用户可以勾选普通用户可查看的页面。
5. 普通用户登录后，只能看到被授权的页面。
6. 普通用户不能访问未授权页面的后端 API。
7. 每个用户不能看到其他人生成的月报。
8. 月报列表、月报详情、月报导出、月报图表、月报修订等相关接口都必须做用户隔离。
9. 整个项目应支持多用户并发访问。
10. 月报异步生成任务、预测异步生成任务不能发生用户串任务、串结果的问题。

---

## 3. 后端修改方案

### 3.1 扩展 User 模型

修改文件：

```text
backend/app/models/user.py
```

当前 `User` 模型只有基础字段：

```python
id
username
hashed_password
role
created_at
```

建议新增字段：

```python
from sqlalchemy import Boolean, Text

allowed_pages_json: Mapped[str] = mapped_column(Text, default="[]")
is_active: Mapped[bool] = mapped_column(Boolean, default=True)
updated_at: Mapped[datetime] = mapped_column(
    DateTime,
    default=now_beijing_naive,
    onupdate=now_beijing_naive,
)
```

建议定义统一页面 key：

```python
ALL_PAGE_KEYS = [
    "dashboard",   # 总览
    "data",        # 数据中心
    "analysis",    # 智能分析
    "prediction",  # 预测分析表
    "forecast",    # 预测模型
    "reports",     # 报告中心
]

ADMIN_PAGE_KEYS = [
    "users",       # 用户管理
    "settings",    # 系统设置
    "monitor",     # 监控日志
]
```

建议给 `User` 增加辅助方法：

```python
import json

def allowed_pages(self) -> list[str]:
    if self.role == "admin":
        return ALL_PAGE_KEYS + ADMIN_PAGE_KEYS
    try:
        return json.loads(self.allowed_pages_json or "[]")
    except json.JSONDecodeError:
        return []
```

如果不希望管理员页面出现在普通页面权限里，可以前端和后端都明确区分：

```python
def business_allowed_pages(self) -> list[str]:
    if self.role == "admin":
        return ALL_PAGE_KEYS
    try:
        return json.loads(self.allowed_pages_json or "[]")
    except json.JSONDecodeError:
        return []
```

---

### 3.2 增加数据库迁移

修改文件：

```text
backend/app/core/migrate.py
```

当前项目已经有轻量迁移逻辑，会为已有表补列。因此继续沿用当前风格。

新增迁移逻辑：

```python
if not _column_exists(engine, "users", "allowed_pages_json"):
    conn.execute(
        text("ALTER TABLE users ADD COLUMN allowed_pages_json TEXT DEFAULT '[]'")
    )

if not _column_exists(engine, "users", "is_active"):
    conn.execute(
        text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
    )

if not _column_exists(engine, "users", "updated_at"):
    conn.execute(
        text("ALTER TABLE users ADD COLUMN updated_at DATETIME")
    )
```

给历史普通用户补默认权限，避免升级后普通用户登录后没有任何页面：

```python
conn.execute(
    text(
        """
        UPDATE users
        SET allowed_pages_json = :pages
        WHERE role != 'admin'
          AND (
            allowed_pages_json IS NULL
            OR allowed_pages_json = ''
            OR allowed_pages_json = '[]'
          )
        """
    ),
    {
        "pages": '["dashboard","data","analysis","prediction","forecast","reports"]'
    },
)
```

---

### 3.3 新增用户管理 API

新增文件：

```text
backend/app/api/users.py
```

在 `backend/app/main.py` 注册：

```python
from app.api import users

app.include_router(users.router, prefix=prefix)
```

所有用户管理接口都必须要求管理员权限：

```python
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)
```

建议接口：

```text
GET    /api/v1/users
POST   /api/v1/users
PUT    /api/v1/users/{user_id}
DELETE /api/v1/users/{user_id}
POST   /api/v1/users/{user_id}/reset-password
GET    /api/v1/users/page-options
```

#### 3.3.1 GET /users

返回用户列表：

```json
[
  {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "allowed_pages": ["dashboard", "data", "analysis", "prediction", "forecast", "reports"],
    "is_active": true,
    "created_at": "2026-06-22T20:00:00+08:00",
    "updated_at": "2026-06-22T20:00:00+08:00"
  }
]
```

#### 3.3.2 POST /users

请求体：

```json
{
  "username": "zhangsan",
  "allowed_pages": ["dashboard", "reports"]
}
```

行为：

- 只创建普通用户。
- `role` 固定为 `user`。
- 初始密码固定为 `qwer1234`。
- 密码必须通过 `hash_password("qwer1234")` 后写入数据库。
- 不允许明文密码入库。
- 用户名必须 trim。
- 用户名不能为空。
- 用户名重复时返回 HTTP 409。

伪代码：

```python
class UserCreateRequest(BaseModel):
    username: str
    allowed_pages: list[str] = []

@router.post("")
def create_user(body: UserCreateRequest, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")

    allowed_pages = validate_allowed_pages(body.allowed_pages)

    user = User(
        username=username,
        hashed_password=hash_password("qwer1234"),
        role="user",
        allowed_pages_json=json.dumps(allowed_pages, ensure_ascii=False),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)
```

#### 3.3.3 PUT /users/{user_id}

请求体：

```json
{
  "allowed_pages": ["dashboard", "data", "reports"],
  "is_active": true
}
```

行为：

- 允许管理员修改普通用户的页面权限。
- 允许管理员启用/停用普通用户。
- 不建议支持把普通用户改成管理员。
- 不允许修改 admin 用户的权限。
- 不允许管理员停用自己。

伪代码：

```python
class UserUpdateRequest(BaseModel):
    allowed_pages: list[str] | None = None
    is_active: bool | None = None

@router.put("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能修改管理员账号")

    if body.allowed_pages is not None:
        user.allowed_pages_json = json.dumps(
            validate_allowed_pages(body.allowed_pages),
            ensure_ascii=False,
        )

    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return serialize_user(user)
```

#### 3.3.4 DELETE /users/{user_id}

行为：

- 允许删除普通用户。
- 禁止删除管理员用户。
- 禁止删除当前登录用户自己。
- 删除用户时不建议删除其月报数据。
- 已存在的月报继续保留 `user_id`。
- 其他普通用户仍然不能看到这些月报。
- 如果以后需要审计，可由数据库层面查询保留数据。

伪代码：

```python
@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账号")

    db.delete(user)
    db.commit()
    return {"id": user_id, "status": "deleted"}
```

#### 3.3.5 POST /users/{user_id}/reset-password

行为：

- 把普通用户密码重置为 `qwer1234`。
- 不允许重置 admin 用户，除非业务明确需要。
- 密码必须 hash 后存储。

伪代码：

```python
@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能重置管理员账号密码")

    user.hashed_password = hash_password("qwer1234")
    db.commit()
    return {"id": user_id, "status": "password_reset", "initial_password": "qwer1234"}
```

#### 3.3.6 GET /users/page-options

返回可勾选页面：

```json
[
  {"key": "dashboard", "label": "总览"},
  {"key": "data", "label": "数据中心"},
  {"key": "analysis", "label": "智能分析"},
  {"key": "prediction", "label": "预测分析表"},
  {"key": "forecast", "label": "预测模型"},
  {"key": "reports", "label": "报告中心"}
]
```

不要把 `settings`、`monitor`、`users` 放给普通用户勾选。

---

### 3.4 扩展登录接口和当前用户接口

修改文件：

```text
backend/app/api/auth.py
```

当前 `/auth/login` 返回：

```python
"user": {
    "id": user.id,
    "username": user.username,
    "role": user.role,
}
```

需要扩展为：

```python
"user": {
    "id": user.id,
    "username": user.username,
    "role": user.role,
    "allowed_pages": serialize_allowed_pages(user),
}
```

`/auth/me` 也要返回同样结构。

登录时增加停用校验：

```python
if not user.is_active:
    raise HTTPException(status_code=403, detail="账号已停用")
```

建议新增统一序列化函数：

```python
def serialize_auth_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "allowed_pages": user.business_allowed_pages()
        if user.role == "admin"
        else user.allowed_pages(),
    }
```

JWT 里可以继续只存：

```python
{"sub": str(user.id), "role": user.role}
```

不要把页面权限只放在 JWT 里，因为管理员修改权限后，希望用户刷新页面或重新请求 `/auth/me` 就能拿到最新权限。

---

### 3.5 增加页面权限依赖

修改文件：

```text
backend/app/core/deps.py
```

新增：

```python
def require_page(page_key: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role == "admin":
            return user
        if page_key not in user.allowed_pages():
            raise HTTPException(status_code=403, detail="无权访问该页面")
        return user
    return dep
```

然后修改各业务 router 的权限依赖。

#### data

修改文件：

```text
backend/app/api/data.py
```

当前 router 是：

```python
router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(get_current_user)])
```

改为：

```python
router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(require_page("data"))])
```

#### analysis

修改文件：

```text
backend/app/api/analysis.py
```

当前 router 是登录即可访问。

改为：

```python
router = APIRouter(
    prefix="/analysis",
    tags=["analysis"],
    dependencies=[Depends(require_page("analysis"))],
)
```

#### forecast

修改文件：

```text
backend/app/api/forecast.py
```

改为：

```python
router = APIRouter(
    prefix="/forecast",
    tags=["forecast"],
    dependencies=[Depends(require_page("forecast"))],
)
```

#### prediction

修改文件：

```text
backend/app/api/prediction.py
```

当前每个接口都使用 `get_current_user`。建议 router 层加：

```python
router = APIRouter(
    prefix="/prediction",
    tags=["prediction"],
    dependencies=[Depends(require_page("prediction"))],
)
```

同时保留接口参数里的 `user: User = Depends(get_current_user)`，用于写入 user_id 和做数据隔离。

#### reports

修改文件：

```text
backend/app/api/reports.py
```

建议 router 层加：

```python
router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_page("reports"))],
)
```

同时保留接口参数里的 `user: User = Depends(get_current_user)`，用于月报隔离。

#### analytics

修改文件：

```text
backend/app/api/analytics.py
```

`analytics` 比较特殊，它既服务总览，也可能服务其他页面图表。

最低修改建议：

```python
@router.get("/dashboard")
def dashboard(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_page("dashboard")),
):
    return AnalyticsService(db).dashboard_summary(start_date, end_date)
```

其他 `/analytics/prices`、`/analytics/charts/{chart_type}` 如果被多个模块复用，可以暂时保持登录即可访问，后续再做更细粒度拆分。

---

## 4. 月报隔离修改方案

### 4.1 严格修改 ReportService 的权限判断

修改文件：

```text
backend/app/services/report.py
```

当前 `ReportService.get_report()` 中有类似逻辑：

```python
if user and user.role != "admin" and report.user_id not in (user.id, None):
    return None
```

这个逻辑存在风险：普通用户可能看到历史 `user_id is None` 的月报。

按需求“每个用户不能看到其他人生成的月报”，建议改成严格隔离：

```python
@staticmethod
def _scope_query(query, user: User | None):
    if user is None:
        return query.filter(False)
    return query.filter(Report.user_id == user.id)

def get_report(self, report_id: int, user: User | None = None) -> Report | None:
    report = self.db.get(Report, report_id)
    if not report:
        return None
    if user is None:
        return None
    if report.user_id != user.id:
        return None
    return report
```

这意味着：

- 普通用户只能看自己的月报。
- 管理员也只能看自己的月报。
- 这最符合“每个用户不能看到其他人生成的月报”。

如果业务希望管理员能审计所有月报，不建议默认放开，而是单独设计一个权限，例如：

```text
view_all_reports
```

否则会和需求描述冲突。

---

### 4.2 历史 user_id 为空的月报归属处理

修改文件：

```text
backend/app/services/user_seed.py
```

当前该文件负责创建默认管理员。

建议在确保默认管理员存在后，把历史 `user_id is NULL` 的月报归属给默认管理员：

```python
from app.models.report import Report

def ensure_default_admin(db: Session) -> None:
    admin = db.query(User).filter(User.username == settings.admin_username).first()
    if not admin:
        admin = User(
            username=settings.admin_username,
            hashed_password=hash_password(settings.admin_password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    db.query(Report).filter(Report.user_id.is_(None)).update(
        {Report.user_id: admin.id}
    )
    db.commit()
```

注意：如果 `ensure_default_admin` 当前逻辑是“只要有任意用户就 return”，需要改掉。否则历史库里已有普通用户但没有 admin 时，会跳过默认管理员创建。

建议新逻辑是：

```python
admin = db.query(User).filter(User.username == settings.admin_username).first()
if not admin:
    create admin
```

不要用：

```python
if db.query(User).count() > 0:
    return
```

---

### 4.3 生成月报时导出 Word 也要传用户

当前 `generate_monthly_draft` 保存 report 后会调用：

```python
docx_path = self.export_docx(report.id)
```

建议改为：

```python
docx_path = self.export_docx(report.id, user)
```

避免后续 `export_docx` 使用严格权限后，因为没有 user 导致查不到报告。

---

### 4.4 月报相关 API 全链路隔离

需要确认以下接口都通过 `ReportService.get_report(report_id, user)` 或等价逻辑校验：

```text
GET    /reports
GET    /reports/{report_id}
PUT    /reports/{report_id}
DELETE /reports/{report_id}
GET    /reports/{report_id}/export
GET    /reports/{report_id}/charts/{chart_id}
POST   /agent/revise/{report_id}
```

其中 `POST /agent/revise/{report_id}` 当前已经先调用 `ReportService(db).get_report(report_id, user)`，继续保留即可。

所有越权访问建议返回 404，而不是 403，以避免泄露其他用户是否有对应 report_id。

---

## 5. 异步任务与并发安全修改方案

### 5.1 月报异步任务必须校验 user_id

修改文件：

```text
backend/app/services/report_tasks.py
backend/app/api/reports.py
```

当前 `ReportGenerateTask` 已经有 `user_id` 字段，创建任务时也传入了当前用户 id。

但是查询任务时需要补充归属校验。

修改 `GET /reports/generate/tasks/{task_id}`：

```python
@router.get("/generate/tasks/{task_id}")
def get_report_task(task_id: str, user: User = Depends(get_current_user)):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task_to_dict(task)
```

### 5.2 预测异步任务也要绑定 user_id

修改文件：

```text
backend/app/services/prediction_tasks.py
backend/app/api/prediction.py
```

当前 `PredictionGenerateTask` 没有 `user_id`，`create_task` 没有接收 `user_id`，`PredictionService.generate()` 在异步任务里也没有传 user。

需要修改：

```python
@dataclass
class PredictionGenerateTask:
    id: str
    status: str = "pending"
    step: int = 0
    total_steps: int = 7
    step_label: str = ""
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    user_id: int | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
```

修改 create_task：

```python
def create_task(
    total_steps: int = 7,
    body: PredictionGenerateRequest | None = None,
    user_id: int | None = None,
) -> PredictionGenerateTask:
    if body and body.unrestricted_mode:
        total_steps = 1
    task = PredictionGenerateTask(
        id=uuid.uuid4().hex,
        total_steps=total_steps,
        user_id=user_id,
        message="任务已创建，等待执行…",
    )
    with _lock:
        _tasks[task.id] = task
    return task
```

修改 `generate_prediction_async`：

```python
@router.post("/generate/async")
def generate_prediction_async(
    body: PredictionGenerateRequest,
    user: User = Depends(get_current_user),
):
    task = create_task(body=body, user_id=user.id)
    start_task(task.id, body)
    return task_to_dict(task)
```

修改 `get_prediction_task`：

```python
@router.get("/generate/tasks/{task_id}")
def get_prediction_task(task_id: str, user: User = Depends(get_current_user)):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task_to_dict(task)
```

修改 `_run_task`，异步生成时重新查询用户并传入：

```python
from app.models.user import User

task = get_task(task_id)
user = None
if task and task.user_id:
    user = db.query(User).filter(User.id == task.user_id).first()

result = PredictionService(db).generate(
    symbol=body.symbol,
    year=body.year,
    month=body.month,
    provider=body.model_provider,
    model=body.model_name,
    mode=body.mode,
    extra_instruction=body.extra_instruction,
    on_progress=on_progress,
    trusted_sources_only=body.trusted_sources_only,
    unrestricted_mode=body.unrestricted_mode,
    user=user,
)
```

---

### 5.3 SQLite 并发优化

修改文件：

```text
backend/app/core/database.py
```

当前 engine 配置：

```python
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
```

建议改为：

```python
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)
```

增加 SQLite PRAGMA：

```python
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

这可以降低并发读写时出现 `database is locked` 的概率。

---

### 5.4 多 worker 并发注意事项

当前月报和预测异步任务都用进程内存字典保存任务状态：

```python
_tasks: dict[str, ReportGenerateTask] = {}
_tasks: dict[str, PredictionGenerateTask] = {}
```

这只能支持单进程服务。

如果使用：

```bash
uvicorn app.main:app --workers 4
```

会出现问题：

- worker A 创建任务。
- worker B 收到轮询请求。
- worker B 的内存里没有该 task_id。
- 前端看到“任务不存在或已过期”。

生产环境建议把任务状态迁移到数据库或 Redis。

最低建议新增数据库表：

```text
generation_tasks
- id
- task_type              # report | prediction
- user_id
- status
- step
- total_steps
- step_label
- message
- result_json
- error
- started_at
- finished_at
- updated_at
```

如果本期不做数据库任务表，至少在部署文档中明确：

```text
当前异步任务状态为单进程内存态。
生产部署时 uvicorn/gunicorn worker 数必须为 1。
如需多 worker，需要先把任务状态迁移到数据库或 Redis。
```

---

## 6. 前端修改方案

### 6.1 扩展 AuthUser

修改文件：

```text
frontend/src/lib/authStorage.ts
```

当前：

```ts
export interface AuthUser {
  id: number
  username: string
  role: 'admin' | 'user'
}
```

改为：

```ts
export interface AuthUser {
  id: number
  username: string
  role: 'admin' | 'user'
  allowed_pages: string[]
}
```

---

### 6.2 扩展 AuthContext

修改文件：

```text
frontend/src/contexts/AuthContext.tsx
```

当前 `AuthContextValue` 包含：

```ts
user
token
loading
login
logout
isAdmin
```

新增：

```ts
canAccessPage: (page: string) => boolean
```

实现：

```ts
const canAccessPage = useCallback(
  (page: string) => user?.role === 'admin' || Boolean(user?.allowed_pages?.includes(page)),
  [user],
)
```

加入 value：

```ts
const value = useMemo(
  () => ({
    user,
    token,
    loading,
    login,
    logout,
    isAdmin: user?.role === 'admin',
    canAccessPage,
  }),
  [user, token, loading, login, logout, canAccessPage],
)
```

---

### 6.3 新增 PageRoute

新增文件：

```text
frontend/src/components/PageRoute.tsx
```

内容建议：

```tsx
import { Navigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function PageRoute({
  page,
  children,
}: {
  page: string
  children: React.ReactNode
}) {
  const { user, loading, canAccessPage } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-white/60">
        加载中…
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!canAccessPage(page)) {
    return (
      <div className="py-16 text-center">
        <div className="text-lg font-medium text-white/90">无权访问</div>
        <p className="mt-2 text-sm text-white/50">请联系管理员开通该页面权限</p>
      </div>
    )
  }

  return <>{children}</>
}
```

---

### 6.4 修改 App 路由

修改文件：

```text
frontend/src/App.tsx
```

当前主要业务页面登录即可访问，只有 `settings`、`monitor` 走 `AdminRoute`。

引入：

```ts
import PageRoute from './components/PageRoute'
import UserManagement from './pages/UserManagement'
```

修改业务页面路由：

```tsx
<Route
  index
  element={
    <PageRoute page="dashboard">
      <Dashboard />
    </PageRoute>
  }
/>

<Route
  path="data"
  element={
    <PageRoute page="data">
      <DataCenter />
    </PageRoute>
  }
/>

<Route
  path="analysis"
  element={
    <PageRoute page="analysis">
      <Analysis />
    </PageRoute>
  }
/>

<Route
  path="forecast"
  element={
    <PageRoute page="forecast">
      <Forecast />
    </PageRoute>
  }
/>

<Route
  path="prediction"
  element={
    <PageRoute page="prediction">
      <Prediction />
    </PageRoute>
  }
/>

<Route
  path="reports"
  element={
    <PageRoute page="reports">
      <ReportCenter />
    </PageRoute>
  }
/>
```

新增用户管理路由：

```tsx
<Route
  path="users"
  element={
    <AdminRoute>
      <UserManagement />
    </AdminRoute>
  }
/>
```

---

### 6.5 修改导航栏

修改文件：

```text
frontend/src/components/Layout.tsx
```

当前 `navItems` 固定展示，管理员额外展示 `settings`、`monitor`。

改为每个业务导航带 key：

```ts
const navItems = [
  { key: 'dashboard', to: '/', label: '总览' },
  { key: 'data', to: '/data', label: '数据中心' },
  { key: 'analysis', to: '/analysis', label: '智能分析' },
  { key: 'prediction', to: '/prediction', label: '预测分析表' },
  { key: 'forecast', to: '/forecast', label: '预测模型' },
  { key: 'reports', to: '/reports', label: '报告中心' },
]
```

管理员导航增加用户管理：

```ts
const adminNavItems = [
  { to: '/users', label: '用户管理' },
  { to: '/settings', label: '系统设置' },
  { to: '/monitor', label: '监控日志' },
]
```

从 `useAuth` 取出 `canAccessPage`：

```ts
const { user, logout, isAdmin, canAccessPage } = useAuth()
```

渲染业务导航时过滤：

```tsx
{navItems
  .filter((item) => canAccessPage(item.key))
  .map((item) => (
    <NavLink key={item.to} to={item.to} ...>
      {item.label}
    </NavLink>
  ))}
```

管理员导航仍然只给管理员展示：

```tsx
{isAdmin &&
  adminNavItems.map((item) => (
    <NavLink key={item.to} to={item.to} ...>
      {item.label}
    </NavLink>
  ))}
```

---

### 6.6 新增用户管理前端 API

修改文件：

```text
frontend/src/api/client.ts
```

新增类型：

```ts
export interface UserPageOption {
  key: string
  label: string
}

export interface ManagedUser {
  id: number
  username: string
  role: 'admin' | 'user'
  allowed_pages: string[]
  is_active: boolean
  created_at?: string
  updated_at?: string
}
```

新增方法：

```ts
export async function getUserPageOptions() {
  const { data } = await api.get<UserPageOption[]>('/users/page-options')
  return data
}

export async function listUsers() {
  const { data } = await api.get<ManagedUser[]>('/users')
  return data
}

export async function createUser(payload: { username: string; allowed_pages: string[] }) {
  const { data } = await api.post<ManagedUser>('/users', payload)
  return data
}

export async function updateUser(
  id: number,
  payload: { allowed_pages?: string[]; is_active?: boolean },
) {
  const { data } = await api.put<ManagedUser>(`/users/${id}`, payload)
  return data
}

export async function deleteUser(id: number) {
  const { data } = await api.delete(`/users/${id}`)
  return data
}

export async function resetUserPassword(id: number) {
  const { data } = await api.post(`/users/${id}/reset-password`)
  return data as { id: number; status: string; initial_password: string }
}
```

---

### 6.7 新增用户管理页面

新增文件：

```text
frontend/src/pages/UserManagement.tsx
```

页面功能：

1. 加载用户列表。
2. 加载页面选项。
3. 新增用户。
4. 勾选页面权限。
5. 保存用户权限。
6. 启用或停用用户。
7. 删除普通用户。
8. 重置普通用户密码为 `qwer1234`。
9. 对 admin 用户禁用删除、重置、权限编辑按钮。

页面结构建议：

```tsx
<div className="space-y-6">
  <div>
    <h1 className="text-2xl font-semibold">用户管理</h1>
    <p className="text-sm text-white/60">
      新增用户、分配页面权限、重置初始密码
    </p>
  </div>

  <div className="glass rounded-2xl p-5">
    新增用户区域
  </div>

  <div className="glass rounded-2xl p-5">
    用户列表与权限勾选区域
  </div>
</div>
```

新增用户区域：

```tsx
<input
  value={newUsername}
  onChange={(e) => setNewUsername(e.target.value)}
  placeholder="请输入用户名"
/>

{pageOptions.map((p) => (
  <label key={p.key}>
    <input
      type="checkbox"
      checked={newAllowedPages.includes(p.key)}
      onChange={...}
    />
    {p.label}
  </label>
))}

<button onClick={handleCreate}>创建用户</button>

<p>初始密码：qwer1234</p>
```

用户列表区域：

```tsx
{users.map((u) => (
  <div key={u.id}>
    <div>
      {u.username}
      {u.role === 'admin' ? '管理员' : '普通用户'}
    </div>

    {pageOptions.map((p) => (
      <label key={p.key}>
        <input
          type="checkbox"
          disabled={u.role === 'admin'}
          checked={u.role === 'admin' || u.allowed_pages.includes(p.key)}
          onChange={...}
        />
        {p.label}
      </label>
    ))}

    <button disabled={u.role === 'admin'} onClick={() => saveUser(u)}>
      保存权限
    </button>

    <button disabled={u.role === 'admin'} onClick={() => resetPassword(u.id)}>
      重置密码
    </button>

    <button disabled={u.role === 'admin'} onClick={() => deleteUser(u.id)}>
      删除
    </button>
  </div>
))}
```

删除和重置密码都必须二次确认：

```ts
if (!window.confirm(`确定删除用户 ${u.username}？`)) return
```

```ts
if (!window.confirm(`确定将 ${u.username} 的密码重置为 qwer1234？`)) return
```

---

## 7. 预测分析表隔离补充建议

虽然本次需求明确提到的是“月报”，但项目里 `predictions` 表也已经有 `user_id` 字段迁移逻辑。

建议检查：

```text
backend/app/models/prediction.py
backend/app/services/prediction.py
```

确保预测分析表也与月报一致：

1. 创建预测分析表时写入 `user_id=user.id`。
2. 普通用户只能看到自己的预测分析表。
3. 详情、更新、修订、导出、删除都必须校验 user_id。
4. 异步预测任务必须绑定 user_id。

这样可以避免“月报隔离做了，但预测分析表仍然串用户”的问题。

---

## 8. 并发支持验收重点

### 8.1 单进程多线程并发

在 SQLite + 单进程 + 多线程情况下，需要确认：

1. 每个请求使用独立 SQLAlchemy Session。
2. 后台异步线程不能复用请求线程的 Session。
3. 后台线程需要自己创建 `SessionLocal()` 并在 finally 中关闭。
4. SQLite 设置 WAL、busy_timeout、timeout。

当前月报异步任务已经自己创建 `SessionLocal()`，这个方向是对的。

### 8.2 多用户并发任务

需要测试：

```text
用户 A 登录 -> 生成月报
用户 B 登录 -> 同时生成月报
用户 A 轮询自己的 task_id
用户 B 轮询自己的 task_id
用户 A 不能查看用户 B 的 task_id
用户 B 不能查看用户 A 的 task_id
最终用户 A 的报告 user_id = A.id
最终用户 B 的报告 user_id = B.id
```

### 8.3 多 worker 部署

如果暂时不迁移任务状态到数据库或 Redis，部署文档必须说明：

```text
当前异步任务状态为进程内存态。
请使用单 worker 部署。
不要使用 uvicorn --workers > 1。
```

如果要真正支持多 worker，需要实现数据库任务表或 Redis。

---

## 9. 测试与验收标准

执行模型完成修改后，按以下标准验收：

### 9.1 管理员能力

1. admin 可以登录。
2. admin 可以看到导航栏中的“用户管理”。
3. admin 可以进入 `/users` 页面。
4. admin 可以创建普通用户。
5. 新建普通用户初始密码为 `qwer1234`。
6. admin 可以为普通用户勾选页面。
7. admin 可以保存普通用户页面权限。
8. admin 可以重置普通用户密码为 `qwer1234`。
9. admin 可以删除普通用户。
10. admin 不能删除自己。
11. admin 不能删除其他 admin。
12. admin 不能误把普通用户改成 admin，除非业务明确实现该能力。

### 9.2 普通用户页面权限

1. 普通用户登录后，只能看到被授权页面的导航项。
2. 普通用户访问未授权前端 URL，显示“无权访问”。
3. 普通用户直接请求未授权页面对应后端 API，返回 403。
4. 管理员修改普通用户权限后，普通用户刷新页面或重新登录后权限生效。

### 9.3 月报隔离

1. 用户 A 生成月报。
2. 用户 B 生成月报。
3. 用户 A 的报告中心只看到 A 自己生成的月报。
4. 用户 B 的报告中心只看到 B 自己生成的月报。
5. 用户 B 直接访问用户 A 的 `/reports/{id}` 返回 404。
6. 用户 B 直接导出用户 A 的 `/reports/{id}/export` 返回 404。
7. 用户 B 直接访问用户 A 的 `/reports/{id}/charts/{chart_id}` 返回 404。
8. 用户 B 调用 `/agent/revise/{report_id}` 修订用户 A 的月报，返回 404。
9. 历史 `user_id is NULL` 的月报不能被普通用户看到。

### 9.4 异步任务隔离

1. 用户 A 创建的 report task，用户 B 查询 task_id 返回 404。
2. 用户 B 创建的 report task，用户 A 查询 task_id 返回 404。
3. 月报异步任务结果里的 report_id 对应 user_id 必须是创建任务的用户。
4. 预测异步任务也必须同样隔离。
5. 并发任务不能互相覆盖进度和结果。

### 9.5 并发稳定性

1. 两个用户同时登录、刷新、查询页面，不应互相影响。
2. 两个用户同时生成月报，任务状态不串。
3. 两个用户同时保存或导出月报，不应覆盖彼此文件。
4. SQLite 不应频繁出现 `database is locked`。
5. 如果使用多 worker 部署，必须先把任务状态迁移到数据库或 Redis。

---

## 10. 重点风险提醒

### 风险 1：只做前端隐藏，没有后端权限

不能只隐藏导航栏。后端 API 必须使用 `require_page` 做权限校验。

否则普通用户可以通过浏览器控制台或 curl 直接访问未授权接口。

### 风险 2：月报列表隔离了，但详情和导出没隔离

必须全链路隔离：

```text
list
detail
update
delete
export
charts
revise
```

只隔离 `GET /reports` 不够。

### 风险 3：异步任务没有校验用户归属

任务接口必须校验：

```python
task.user_id == user.id
```

否则用户只要拿到别人的 task_id，就可能看到别人的生成进度和结果。

### 风险 4：管理员是否能看所有月报要明确

需求说“每个用户不能看到其他人生成的月报”。

严格理解下，管理员也不能看到其他人的月报。

如果产品希望管理员审计所有月报，应新增显式权限，例如：

```text
view_all_reports
```

不要默认让 admin 绕过月报隔离。

### 风险 5：内存任务字典不支持多 worker

当前 `_tasks` 是进程内存态。

如果部署多个 worker，必须改成数据库或 Redis。

---

## 11. 推荐执行顺序

建议执行模型按以下顺序改：

```text
1. 后端 User 模型扩展。
2. 后端 migrate.py 补列。
3. 后端 auth.py 返回 allowed_pages，并校验 is_active。
4. 后端 deps.py 新增 require_page。
5. 后端新增 api/users.py。
6. main.py 注册 users router。
7. 后端业务 API 增加页面权限。
8. ReportService 改严格 user_id 隔离。
9. user_seed.py 处理默认 admin 和历史月报 user_id。
10. report_tasks.py 增强 task user_id 校验。
11. prediction_tasks.py 增加 user_id。
12. database.py 增加 SQLite WAL / timeout / busy_timeout。
13. 前端 AuthUser 增加 allowed_pages。
14. 前端 AuthContext 增加 canAccessPage。
15. 前端新增 PageRoute。
16. 前端 App.tsx 包装业务页面路由。
17. 前端 Layout.tsx 按权限过滤导航，增加用户管理入口。
18. 前端 client.ts 增加 users API。
19. 前端新增 UserManagement.tsx。
20. 手工验收管理员、普通用户、月报隔离、并发任务。
```

---

## 12. 最小可交付版本范围

如果希望先做最小闭环，优先完成：

```text
必须做：
- User.allowed_pages_json
- User.is_active
- 用户管理 API
- auth 返回 allowed_pages
- require_page
- 前端 PageRoute
- 前端用户管理页面
- ReportService 严格隔离 user_id
- report task user_id 校验

建议做：
- prediction task user_id 校验
- SQLite WAL / busy_timeout
- 历史 user_id is NULL 月报归属 admin
- 生产部署单 worker 说明

后续增强：
- 数据库/Redis 持久化任务状态
- 管理员审计所有月报的独立权限
- 用户改密功能
- 强制首次登录修改初始密码
- 操作审计日志
```

---

## 13. 给执行模型的简短指令版

```text
请在 AnalysisAgent 项目中新增用户管理模块，基于现有 auth/JWT/users/require_admin 实现，不要重写认证。

后端：
1. 扩展 User 模型，增加 allowed_pages_json、is_active、updated_at。
2. migrate.py 为 users 补列，并给历史普通用户补默认业务页面权限。
3. auth.py 的 login/me 返回 allowed_pages，并禁止 is_active=false 用户登录。
4. deps.py 新增 require_page(page_key)。
5. 新增 api/users.py，实现管理员用户列表、新增普通用户、修改权限、删除普通用户、重置密码、页面选项接口。新用户初始密码固定 qwer1234，必须 hash 存储。
6. main.py 注册 users router。
7. data/analysis/forecast/prediction/reports 等 API 增加页面权限校验。
8. ReportService 改成严格 user_id 隔离，普通用户和管理员都只能看到自己生成的月报；所有详情、更新、删除、导出、图表都复用该隔离逻辑。
9. agent revise 月报接口继续先通过 ReportService.get_report(report_id, user) 校验。
10. user_seed.py 确保默认 admin 存在，并把历史 user_id 为 NULL 的月报归属给默认 admin。
11. report_tasks.py 查询任务时校验 task.user_id == user.id。
12. prediction_tasks.py 也增加 user_id，异步生成时传 user 给 PredictionService.generate。
13. database.py 为 SQLite 增加 timeout、WAL、busy_timeout，降低并发锁冲突。
14. 如果任务状态仍使用内存 dict，部署文档必须说明只支持单 worker；多 worker 需要数据库或 Redis 任务状态。

前端：
1. AuthUser 增加 allowed_pages。
2. AuthContext 增加 canAccessPage(page)。
3. 新增 PageRoute，根据 allowed_pages 控制页面访问。
4. App.tsx 用 PageRoute 包住 dashboard/data/analysis/prediction/forecast/reports。
5. Layout.tsx 根据 canAccessPage 过滤导航项，管理员导航增加“用户管理”。
6. client.ts 增加 users API。
7. 新增 UserManagement.tsx，支持新增用户、勾选页面权限、保存权限、删除用户、重置密码为 qwer1234。
8. 普通用户未授权页面前端显示“无权访问”，后端 API 返回 403。

验收：
- admin 能创建用户，普通用户用 qwer1234 登录。
- 普通用户只看到授权页面。
- 未授权 API 返回 403。
- 用户 A 看不到用户 B 的月报，包括列表、详情、导出、图表、修订。
- 用户 A 不能查询用户 B 的异步任务状态。
- 并发生成月报不串用户、不串任务、不串结果。
```
