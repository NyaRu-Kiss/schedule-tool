-- WorkBuddy 日程能力：数据库迁移与后端接口契约
--
-- 适用环境：MySQL 8.0+，schedule-tool 现有数据库
-- 用户模型：单用户专属工具，不含 user_id、tenant_id 或组织字段
--
-- 执行前提：
-- 1. 现有表已由 schedule-tool/db.py 初始化：todos、scheduled_tasks、sent_reminders。
-- 2. 本文件是一次性迁移脚本。执行前备份数据库；不要在已成功迁移的库上重复执行。
-- 3. MySQL 不支持 COMMENT ON TABLE/COLUMN 语法；本文件使用 MySQL 原生的列 COMMENT、表 COMMENT。
-- 4. 时间统一以 UTC 存入 DATETIME；timezone 保存语音请求对应的 IANA 时区。
--
-- 设计选择：
-- - todos 继续保存用户表达的待办/日程内容。
-- - scheduled_tasks 继续保存最终安排的时间段，既支持用户指定时间，也支持 Agent 自动排期。
-- - sent_reminders 继续作为提醒成功发送的幂等记录；失败状态留在 scheduled_tasks。
-- - calendar_events 继续保存手动日历事件；Agent 查询档期时需同时考虑它和 scheduled_tasks。
-- - Agent 生成的 SQL 只能由后端受限执行；后端仍需鉴权、校验、限制表/列和参数化执行。
-- - Agent 校验失败重试上限是后端配置，不持久化为一张新表；默认 3 次。

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- -----------------------------------------------------------------------------
-- 接口契约（供后端/MCP/Agent 实现；此处为设计，不会由 SQL 创建 HTTP 路由）
-- -----------------------------------------------------------------------------
-- 调用链固定为 WorkBuddy -> 日程 MCP -> 日程 Agent -> 日程后端 -> MySQL。
-- MCP 只转发请求和结果，不调用数据库；Agent 负责理解用户文本、生成受限 SQL 和绑定参数，
-- 并在用户未指定开始时间时计算候选档期；后端负责最终授权、校验、SQL 执行和事务。
--
-- MCP 工具：create_schedule、poll_reminders、ack_reminder。
-- MCP 只转发 WorkBuddy 请求给 Agent；Agent 生成 SQL statements 和绑定参数。
--
-- Agent -> 后端唯一内部入口：POST /api/internal/sql/execute。
-- 兼容保留的 SQL_BATCH 仅允许只读 SELECT；创建、自动排期和提醒确认等写操作
-- 必须使用专用 operation，由后端执行业务模板和冲突/状态校验。
-- Request:
-- {
--   "request_id": "uuid",
--   "attempt": 1,
--   "max_attempts": 3,
--   "operation": "CREATE_SCHEDULE",
--   "statements": [{"sql":"...","params":[...]}]
-- }
-- 后端只允许参数化 SELECT/INSERT/UPDATE，且只允许访问 todos、scheduled_tasks、
-- calendar_events、sent_reminders 的白名单字段。所有 statements 在单事务中执行。
-- 服务认证仅用于 Agent 调用本内部 SQL 接口，凭据由服务部署配置提供。
-- 电脑和手机前端及其普通 /api/* 接口无需登录、密码或访问令牌；
-- 前端不持有内部服务令牌，普通 API 仍执行参数、业务限制和冲突校验。
-- attempt 是完整尝试轮次，范围为 1..3（包含首次）；每轮可包含查询和创建，只有顶层 retryable=true 的错误允许 Agent 修正后重试。
-- 成功响应包含 request_id、attempt、transaction=COMMITTED 和各 statement 结果摘要。
-- 失败响应包含 request_id、attempt、retryable 和稳定 error.code/error.message。
--
-- 自动排期的 SELECT 必须同时查询 scheduled_tasks 和 calendar_events；Agent 计算空闲时间
-- 后再提交 todos + scheduled_tasks 的创建事务。
-- T05: FIND_AVAILABLE_SLOTS 的 date/end_date 为用户时区内含首尾的日期范围；
-- 默认只查询目标日期，且必须在今天起 SCHEDULE_HORIZON_DAYS 个日历日内。
-- 后端只返回两类占用的 ISO 日期/时间行，不计算候选、不缓存查询；
-- Agent 按 WORK_HOURS、默认 30 分钟、截止时间和 5 分钟粒度计算空档。
-- 提醒成功确认必须在一个事务中 UPDATE scheduled_tasks 并 INSERT sent_reminders；
-- 提醒失败只 UPDATE scheduled_tasks 的失败状态和错误字段，不写 sent_reminders。
--
-- 统一错误 JSON: {"retryable":true,"error":{"code":"TIME_CONFLICT","message":"..."}}
-- 错误码建议：INVALID_ARGUMENT、TIME_CONFLICT、POLICY_LIMIT、NO_AVAILABLE_SLOT、NOT_FOUND、PERMISSION_DENIED、SQL_NOT_ALLOWED、IDEMPOTENCY_CONFLICT、INTERNAL_ERROR。
-- Agent 只对顶层 retryable=true 的错误修正请求后重试；默认最多 3 轮完整尝试，可由后端配置，
-- 达上限后停止调用并将最终错误返回 WorkBuddy。非 retryable 错误不重试。

-- -----------------------------------------------------------------------------
-- todos 扩展
-- -----------------------------------------------------------------------------
-- 保留既有待办主表。增加时区和请求幂等标识，使 WorkBuddy 创建请求可追踪、可去重。
-- deadline / estimate_min / source / raw_input 等既有字段继续沿用。
ALTER TABLE `todos`
    MODIFY COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT '待办主键；由旧版和 WorkBuddy 创建流程共用',
    MODIFY COLUMN `title` VARCHAR(500) NOT NULL COMMENT '待办或日程标题',
    MODIFY COLUMN `priority` INT NOT NULL DEFAULT 2 COMMENT '优先级：1=高、2=中、3=低',
    MODIFY COLUMN `deadline` DATETIME NULL COMMENT '截止时间；有值时自动排期不得晚于此时间，UTC',
    MODIFY COLUMN `estimate_min` INT NULL COMMENT '预计时长，分钟；自动排期时必须有有效时长',
    MODIFY COLUMN `scheduled` TINYINT NOT NULL DEFAULT 0 COMMENT '是否已生成排期：0=否、1=是；旧接口继续使用',
    MODIFY COLUMN `done` TINYINT NOT NULL DEFAULT 0 COMMENT '待办是否已完成：0=否、1=是',
    MODIFY COLUMN `source` VARCHAR(100) NULL COMMENT '创建来源，例如 cli、api、workbuddy',
    MODIFY COLUMN `raw_input` TEXT NULL COMMENT '用户原始文本；可用于 Agent 理解和问题追踪',
    MODIFY COLUMN `created_at` DATETIME NOT NULL COMMENT '待办创建时间；新写入按 UTC 存储',
    MODIFY COLUMN `updated_at` DATETIME NOT NULL COMMENT '待办最后更新时间；新写入按 UTC 存储',
    ADD COLUMN `timezone` VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'
        COMMENT '该待办/日程使用的 IANA 时区，例如 Asia/Shanghai' AFTER `raw_input`,
    ADD COLUMN `request_id` VARCHAR(64) NULL
        COMMENT 'WorkBuddy 请求全链路 ID；用于创建请求追踪与幂等处理' AFTER `timezone`,
    ADD COLUMN `auto_scheduled` TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否由 Agent 自动寻找空闲档期：0=用户指定时间，1=自动排期' AFTER `request_id`,
    ADD UNIQUE KEY `uk_todos_request_id` (`request_id`),
    COMMENT = '待办主表；WorkBuddy 日程请求沿用本表，不新增日程主表';

-- -----------------------------------------------------------------------------
-- scheduled_tasks 扩展
-- -----------------------------------------------------------------------------
-- 保留既有排期表和 todo_id 外键。此表的一行是实际占用的时间段。
-- reminder_at 默认为 NULL，迁移时不擅自改变历史提醒时刻；新建记录由后端写入提醒时间。
ALTER TABLE `scheduled_tasks`
    MODIFY COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT '排期主键；也作为一条提醒的关联标识',
    MODIFY COLUMN `todo_id` INT NOT NULL COMMENT '关联 todos.id；排期来源的待办或日程',
    MODIFY COLUMN `start_at` DATETIME NOT NULL COMMENT '最终排期开始时间；新写入按 UTC 存储',
    MODIFY COLUMN `end_at` DATETIME NOT NULL COMMENT '最终排期结束时间；新写入按 UTC 存储',
    MODIFY COLUMN `reminder_sent` TINYINT NOT NULL DEFAULT 0 COMMENT '旧接口提醒发送标记：0=未发、1=已发；新流程同时更新 reminder_status',
    MODIFY COLUMN `done` TINYINT NOT NULL DEFAULT 0 COMMENT '旧接口完成标记：0=未完成、1=已完成；新流程同时更新 status',
    MODIFY COLUMN `created_at` DATETIME NOT NULL COMMENT '排期创建时间；新写入按 UTC 存储',
    ADD COLUMN `timezone` VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'
        COMMENT '该排期时间段对应的 IANA 时区' AFTER `end_at`,
    ADD COLUMN `schedule_source` VARCHAR(20) NOT NULL DEFAULT 'MANUAL'
        COMMENT '时间来源：MANUAL=用户指定，AUTO=Agent 自动排期' AFTER `timezone`,
    ADD COLUMN `status` VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        COMMENT '排期状态：ACTIVE、CANCELLED、COMPLETED；历史 done=1 数据迁移为 COMPLETED' AFTER `done`,
    ADD COLUMN `reminder_at` DATETIME NULL
        COMMENT '提醒触发时间，UTC；NULL 表示未配置提醒' AFTER `reminder_sent`,
    ADD COLUMN `reminder_status` VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        COMMENT '提醒状态：PENDING、PROCESSING、SENT、FAILED、CANCELLED' AFTER `reminder_at`,
    ADD COLUMN `reminder_idempotency_key` VARCHAR(128) NULL
        COMMENT '提醒发送幂等键；同一排期的提醒重试保持不变' AFTER `reminder_status`,
    ADD COLUMN `reminder_attempt_count` INT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '提醒发送尝试次数' AFTER `reminder_idempotency_key`,
    ADD COLUMN `reminder_last_attempt_at` DATETIME NULL
        COMMENT '最近一次提醒发送尝试时间，UTC' AFTER `reminder_attempt_count`,
    ADD COLUMN `reminder_error` VARCHAR(1000) NULL
        COMMENT '最近一次提醒发送失败原因' AFTER `reminder_last_attempt_at`,
    ADD KEY `idx_scheduled_tasks_status_time` (`status`, `start_at`, `end_at`),
    ADD KEY `idx_scheduled_tasks_due_reminder` (`reminder_status`, `reminder_at`),
    ADD UNIQUE KEY `uk_scheduled_tasks_reminder_key` (`reminder_idempotency_key`),
    COMMENT = '最终排期表；兼容旧版待办排期、指定时间日程及 Agent 自动排期';

-- 将既有完成状态同步到新增状态字段，保证旧数据参与新查询时语义一致。
UPDATE `scheduled_tasks`
   SET `status` = 'COMPLETED'
 WHERE `done` = 1 AND `status` = 'ACTIVE';

UPDATE `scheduled_tasks`
   SET `reminder_status` = 'SENT'
 WHERE `reminder_sent` = 1 AND `reminder_status` = 'PENDING';

-- -----------------------------------------------------------------------------
-- calendar_events 注释与排期查询索引
-- -----------------------------------------------------------------------------
-- calendar_events 是现有日历界面的手动事件表，不替换 scheduled_tasks。
-- Agent 自动排期必须将两张表中的有效时间段合并后再选择空档。
ALTER TABLE `calendar_events`
    MODIFY COLUMN `id` VARCHAR(64) NOT NULL COMMENT '日历事件主键',
    MODIFY COLUMN `type_id` VARCHAR(64) NOT NULL COMMENT '事件类型 ID，关联 event_types.id',
    MODIFY COLUMN `title` VARCHAR(255) NOT NULL COMMENT '手动日历事件标题',
    MODIFY COLUMN `event_date` DATE NOT NULL COMMENT '事件日期，按用户日历时区解释',
    MODIFY COLUMN `start_time` TIME NOT NULL COMMENT '事件开始时间',
    MODIFY COLUMN `end_time` TIME NOT NULL COMMENT '事件结束时间',
    MODIFY COLUMN `note` VARCHAR(1000) NULL COMMENT '手动日历事件备注',
    ADD KEY `idx_calendar_events_date_time` (`event_date`, `start_time`, `end_time`),
    COMMENT = '手动日历事件表；自动排期时作为已占用时间来源之一';

-- -----------------------------------------------------------------------------
-- sent_reminders 扩展
-- -----------------------------------------------------------------------------
-- 保留现有 UNIQUE(scheduled_task_id) 去重约束，增加幂等键。
-- 本表只写成功发送的提醒；失败尝试保存在 scheduled_tasks 的提醒状态和错误字段。
ALTER TABLE `sent_reminders`
    MODIFY COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT '已发送提醒记录主键',
    MODIFY COLUMN `scheduled_task_id` INT NOT NULL COMMENT '关联 scheduled_tasks.id；现有唯一约束保证同一排期只成功提醒一次',
    MODIFY COLUMN `sent_at` DATETIME NOT NULL COMMENT '提醒成功发送时间；新写入按 UTC 存储',
    ADD COLUMN `idempotency_key` VARCHAR(128) NULL
        COMMENT '发送确认幂等键；与 scheduled_tasks.reminder_idempotency_key 对应' AFTER `sent_at`,
    ADD UNIQUE KEY `uk_sent_reminders_idempotency_key` (`idempotency_key`),
    COMMENT = '已成功发送的提醒去重记录；失败尝试不写入此表';

-- -----------------------------------------------------------------------------
-- 数据库迁移后检查
-- -----------------------------------------------------------------------------
-- 检查新列和详细列注释：
-- SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
--   FROM information_schema.COLUMNS
--  WHERE TABLE_SCHEMA = DATABASE()
--    AND TABLE_NAME IN ('todos', 'scheduled_tasks', 'sent_reminders')
--  ORDER BY TABLE_NAME, ORDINAL_POSITION;
--
-- 检查新索引：
-- SHOW INDEX FROM `todos`;
-- SHOW INDEX FROM `scheduled_tasks`;
-- SHOW INDEX FROM `sent_reminders`;

-- T11 远程接入：独立 Streamable HTTP /mcp（无会话 JSON 响应），仍只转发至 Agent。
-- MCP HTTP 使用独立入口 Bearer 令牌和 Origin 白名单；普通前端 API 免认证不变。
-- 不新增数据库表或变更 SQL 接口；真实 WorkBuddy 验收需要可达 HTTPS 地址。

-- 本周演示数据：写入 7800 使用的 calendar_events，周日不插入。
INSERT IGNORE INTO `event_types` (`id`, `name`, `color`, `sort_order`) VALUES
  ('meeting', '会议', '#3b82f6', 1),
  ('on-site', '现场活动', '#f59e0b', 2),
  ('external', '外部项目', '#8b5cf6', 3),
  ('work', '工作', '#10b981', 4),
  ('social', '社交', '#ef4444', 5),
  ('dating', '恋爱', '#3b82f6', 6);

INSERT IGNORE INTO `calendar_events`
  (`id`, `type_id`, `title`, `event_date`, `start_time`, `end_time`, `note`) VALUES
  ('demo-20261005-planning', 'meeting', '季度项目规划', '2026-10-05', '08:30:00', '10:00:00', '明确本周目标与交付节点'),
  ('demo-20261005-deepwork', 'work', '产品方案深度工作', '2026-10-05', '14:00:00', '16:30:00', '完成核心流程与评审材料'),
  ('demo-20261006-review', 'external', '客户需求评审', '2026-10-06', '09:00:00', '11:00:00', '同步需求范围和验收标准'),
  ('demo-20261006-training', 'on-site', '团队培训', '2026-10-06', '15:30:00', '17:00:00', '新流程与工具培训'),
  ('demo-20261007-design', 'work', '界面设计打磨', '2026-10-07', '10:00:00', '12:00:00', '整理交互细节与视觉规范'),
  ('demo-20261007-sync', 'meeting', '跨团队同步会', '2026-10-07', '19:00:00', '20:30:00', '同步依赖事项与风险'),
  ('demo-20261008-interview', 'external', '合作方访谈', '2026-10-08', '08:00:00', '09:30:00', '收集一线使用反馈'),
  ('demo-20261008-writing', 'work', '周报与文档整理', '2026-10-08', '13:30:00', '15:00:00', '更新项目文档与周报'),
  ('demo-20261009-demo', 'meeting', '版本演示准备', '2026-10-09', '09:30:00', '11:30:00', '准备演示脚本与数据'),
  ('demo-20261009-social', 'social', '团队聚餐', '2026-10-09', '18:30:00', '20:30:00', '团队交流'),
  ('demo-20261010-focus', 'work', '周末收尾工作', '2026-10-10', '10:00:00', '12:00:00', '完成遗留事项与下周计划'),
  ('demo-20261010-outdoor', 'on-site', '户外活动', '2026-10-10', '15:00:00', '17:00:00', '放松与团队活动');
