# 共享单车调度因子研究

偏相关与滞后相关的真实业务分析小型项目。完整模拟客户、痛点、上下游、算法公式与一天工作剧本见 [BUSINESS.md](BUSINESS.md)。

## 模块与业务流程
数据接入（JSON/CSV、字段验证、批次指纹）→ 日批对账（设备文件与调度台按站点时段核对，缺失/重复/冲突挂起，确认后切换研究批次）→ 参数化分析（异步 Python worker）→ 结果复核（指标、图形、明细、解释、批准）→ 定时分发（本地收件箱、CSV/JSON、SHA256）；另有业务总览和审计轨迹。
三个贯穿全栈的实体：Dataset 数据批次、Job 分析任务、Report 分发计划；辅助 User、Audit、Delivery，以及日批对账实体 ReconBatch、SourceRecord、ReconDifference、ReconRelease。

## 日批对账（两来源核对）
设备文件与调度台都上报站点时段观测，直接合并会带入重复、缺失或冲突。系统按 `batch_key`（日批）+ 站点 + 时段核对两来源：
- **来源留存不覆盖**：两来源明细分别存入 `source_records`，同站同时段重复条目以 `seq` 各自保留，任何合并都不丢原始记录。
- **差异先挂起**：缺失（仅一来源有）、重复（同来源多条）、数值冲突（两来源取值不一致）分别记入 `recon_differences`，可逐项或一次性“采用来源”。
- **确认才入研究侧**：未确认批次与分析侧物理隔离，分析任务只能选到已确认生成的不可变 Dataset（`origin=recon`）；管理员确认后一次性切换。
- **幂等与续跑**：重跑同日批、重传内容一致的同一来源不新增记录；重复确认内容未变则复用原研究批次，失败可续跑且不重复生成批次。
- **补齐只重开受影响批次**：已确认批次收到新数据仅重开该批次，重新确认后升版（v1→v2）生成新 Dataset；旧 Dataset 保留，已运行、已批准的 Job 与简报始终固定在原批次。
- **可追溯**：`recon_releases` 记录每次确认的版本、研究批次去向、内容指纹、确认人与说明；页面“日批对账”可查看差异、采用来源与批次去向。
接口前缀 `/recon`：上传来源 `POST /recon/sources`、批次列表/详情、`POST /recon/batches/{id}/resolve`、`POST /recon/batches/{id}/confirm`（仅 admin）。


## 快速启动
```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18202；后端文档 http://localhost:19202/docs；数据库宿主端口 17702。
`SEED_DEMO=true` 自动幂等 seed；不覆盖用户修改。手动 seed 命令可重复执行。

## 演示账号与权限
|账号|密码|真实权限|
|---|---|---|
|admin@demo.local|Demo123!|接入、执行、批准、分发、暂停、读取与下载|
|analyst@demo.local|Demo123!|接入、执行、读取与下载；不能批准或安排分发|
|viewer@demo.local|Demo123!|只读与下载|

## 技术与本地开发
Python 3.12 / FastAPI / SQLAlchemy / NumPy / SciPy / scikit-learn；PostgreSQL 16；Redis 7；Nginx；原生 HTML CSS JavaScript ES modules（用户指定）。后端所有校验、持久化和算法在服务端。无前端打包步骤。
后端：安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET、ARTIFACT_DIR 后在 backend/ 执行 `python -m migrations.initial`、`python -m scripts.seed_demo`、`uvicorn src.main:app`，另开 `python -m src.worker`。前端使用带 /api 反向代理的 Nginx，直接打开 index.html 不支持 API。

## 目录与工程约定
backend/src/{models,schemas,services,routes,controllers,middlewares,constants,config,utils}；backend/scripts/seed_demo.py；backend/migrations/initial.py。
frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。
Role 枚举：admin/analyst/viewer；JobStatus：queued/running/completed/failed。后端 backend/src/constants/enums.py，前端 frontend/src/constants/enums.js；路由权限在 middlewares/auth.py；页面按相同角色控制操作入口。

## 环境变量与 Docker
COMPOSE_PROJECT_NAME=cycle-factors；FRONTEND_PORT=18202；BACKEND_PORT=19202；DB_PORT=17702；DB_PASSWORD、JWT_SECRET 见 .env.example；SEED_DEMO 默认 true。共享命名产物卷供后端下载与 worker 写入，数据库/Redis 各持久卷。
恰好五服务均有健康检查。Redis 队列加 SQL 排队状态兜底；worker 按 next_run 生成本地收件箱文件。周期 60 秒至 30 天。分发结果为批准分析的固定快照；若需新数据重新计算并建立新计划。当前不连接邮件或企业聊天。
错误响应、请求编号、Redis 每 IP 每分钟 240 次限流、JWT 和数据库操作审计。演示密钥与密码仅供本机模拟；生产部署前配置独立密钥与账号。

## 数据与验收
所有数据为固定随机种子生成的模拟业务数据，不能作为实际生产决策证据。项目独立算法、输入边界及业务局限详见 BUSINESS.md。测试与截图统一存放 ../../test-artifacts/gb-1003/，源码不含日志/截图/测试报告。
清理本项目演示数据：`docker compose down -v --remove-orphans`（会删除本项目命名卷）。

## License
MIT，见 LICENSE。
