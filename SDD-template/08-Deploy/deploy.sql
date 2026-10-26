-- ============================================================
-- T00: VOV_DealerVehicleInspectTask 表结构维护
-- 数据库：PvUCM
-- 说明：
--   表已存在（旧版本），通过 ALTER TABLE 增删字段对齐新版技术方案
--   幂等：重复执行不会报错
-- ============================================================

USE [PvUCM];
GO

-- ① 新增字段（旧表没有的字段）
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'Source')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [Source] NVARCHAR(20) NOT NULL CONSTRAINT DF_InspectTask_Source DEFAULT N'MANUAL';

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'LtoTaskId')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [LtoTaskId] NVARCHAR(100) NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'CarSeries')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [CarSeries] NVARCHAR(50) NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'DrivingLicensePhoto')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [DrivingLicensePhoto] NTEXT NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'IsFrameAccident')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [IsFrameAccident] BIT NOT NULL CONSTRAINT DF_InspectTask_IsFrameAccident DEFAULT 0;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'FrameAccidentPhotos')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [FrameAccidentPhotos] NTEXT NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'PaintThicknessData')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [PaintThicknessData] NTEXT NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'IsPriceNegotiable')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [IsPriceNegotiable] BIT NOT NULL CONSTRAINT DF_InspectTask_IsPriceNegotiable DEFAULT 0;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'EstimatedPrice')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [EstimatedPrice] DECIMAL(18,2) NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'TotalTransactionPrice')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [TotalTransactionPrice] DECIMAL(18,2) NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'ResidualValueAmount')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [ResidualValueAmount] DECIMAL(18,2) NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'SubsidyAmount')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [SubsidyAmount] DECIMAL(18,2) NULL;

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'VOV_DealerVehicleInspectTask' AND COLUMN_NAME=N'InspectTime')
    ALTER TABLE [dbo].[VOV_DealerVehicleInspectTask] ADD [InspectTime] DATETIME NULL;

-- ② 索引（幂等）
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name=N'IX_InspectTask_ReportToken' AND object_id=OBJECT_ID(N'VOV_DealerVehicleInspectTask'))
    CREATE UNIQUE INDEX [IX_InspectTask_ReportToken]
        ON [dbo].[VOV_DealerVehicleInspectTask] ([ReportToken])
        WHERE [ReportToken] IS NOT NULL;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name=N'IX_InspectTask_DealerCode_CreateTime' AND object_id=OBJECT_ID(N'VOV_DealerVehicleInspectTask'))
    CREATE INDEX [IX_InspectTask_DealerCode_CreateTime]
        ON [dbo].[VOV_DealerVehicleInspectTask] ([DealerCode], [CreateTime] DESC);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name=N'IX_InspectTask_Status_CreateTime' AND object_id=OBJECT_ID(N'VOV_DealerVehicleInspectTask'))
    CREATE INDEX [IX_InspectTask_Status_CreateTime]
        ON [dbo].[VOV_DealerVehicleInspectTask] ([ReportStatus], [CreateTime] DESC);

-- ③ 验证最终字段数
SELECT COUNT(*) AS ColumnCount FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = N'VOV_DealerVehicleInspectTask';
GO

-- ============================================================
-- T01: 检测项字典数据初始化
-- 数据库：PvUCM
-- 说明：
--   新增三条分类（skeleton/exterior/interior），Code 用字符串与旧数字 Code 区分
--   按 PRD 3.3.3 检测项清单插入 Item 和 Option 数据
--   幂等：重复执行不会报错，已有数据跳过
-- ============================================================

USE [PvUCM];
GO

-- ① 插入三条新分类
IF NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectCategory WHERE Code = N'skeleton')
    INSERT INTO VOV_DealerVehicleInspectCategory (Code, Name, CreateTime) VALUES (N'skeleton', N'骨架', GETDATE());
IF NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectCategory WHERE Code = N'exterior')
    INSERT INTO VOV_DealerVehicleInspectCategory (Code, Name, CreateTime) VALUES (N'exterior', N'外观', GETDATE());
IF NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectCategory WHERE Code = N'interior')
    INSERT INTO VOV_DealerVehicleInspectCategory (Code, Name, CreateTime) VALUES (N'interior', N'内饰', GETDATE());

-- ② 插入检测项（用子查询获取分类ID，避免跨批次变量失效）
-- 骨架 - 检测部位（2项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'检测部位',N'车顶',     N'sk_001',1),
    (N'检测部位',N'水箱框架', N'sk_002',2)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'skeleton'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 骨架 - 前部检测（12项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'前部检测',N'左前灯架-车辆支架', N'sk_003',3),
    (N'前部检测',N'右前灯架-车辆支架', N'sk_004',4),
    (N'前部检测',N'前防撞横梁',         N'sk_005',5),
    (N'前部检测',N'左前梁头',           N'sk_006',6),
    (N'前部检测',N'左前纵梁',           N'sk_007',7),
    (N'前部检测',N'左前翼子板内板',     N'sk_008',8),
    (N'前部检测',N'左前减震器座',       N'sk_009',9),
    (N'前部检测',N'右前梁头',           N'sk_010',10),
    (N'前部检测',N'右前纵梁',           N'sk_011',11),
    (N'前部检测',N'右前翼子板内板',     N'sk_012',12),
    (N'前部检测',N'右前减震器座',       N'sk_013',13),
    (N'前部检测',N'防火墙',             N'sk_014',14)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'skeleton'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 骨架 - 左部检测（7项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'左部检测',N'左上边梁骨架',   N'sk_015',15),
    (N'左部检测',N'左下边梁',       N'sk_016',16),
    (N'左部检测',N'左A柱骨架',      N'sk_017',17),
    (N'左部检测',N'左B柱骨架',      N'sk_018',18),
    (N'左部检测',N'左C柱骨架',      N'sk_019',19),
    (N'左部检测',N'左D柱骨架',      N'sk_020',20),
    (N'左部检测',N'左后翼子板内板', N'sk_021',21)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'skeleton'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 骨架 - 后部检测（12项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'后部检测',N'左后灯架-车辆支架',   N'sk_022',22),
    (N'后部检测',N'右后灯架-车辆支架',   N'sk_023',23),
    (N'后部检测',N'后围板',               N'sk_024',24),
    (N'后部检测',N'后备箱底板（备胎槽）',N'sk_025',25),
    (N'后部检测',N'后防撞横梁',           N'sk_026',26),
    (N'后部检测',N'左后纵梁',             N'sk_027',27),
    (N'后部检测',N'左后梁头',             N'sk_028',28),
    (N'后部检测',N'左后减震器座',         N'sk_029',29),
    (N'后部检测',N'右后梁头',             N'sk_030',30),
    (N'后部检测',N'右后纵梁',             N'sk_031',31),
    (N'后部检测',N'右后减震器座',         N'sk_032',32),
    (N'后部检测',N'后窗台板',             N'sk_033',33)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'skeleton'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 骨架 - 右部检测（7项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'右部检测',N'右后翼子板内板', N'sk_034',34),
    (N'右部检测',N'右上边梁骨架',   N'sk_035',35),
    (N'右部检测',N'右下边梁',       N'sk_036',36),
    (N'右部检测',N'右D柱骨架',      N'sk_037',37),
    (N'右部检测',N'右C柱骨架',      N'sk_038',38),
    (N'右部检测',N'右B柱骨架',      N'sk_039',39),
    (N'右部检测',N'右A柱骨架',      N'sk_040',40)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'skeleton'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 外观 - 检测部位（21项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'检测部位',N'前挡风玻璃',   N'ex_001',1),
    (N'检测部位',N'发动机盖',     N'ex_002',2),
    (N'检测部位',N'左前车灯',     N'ex_003',3),
    (N'检测部位',N'右前车灯',     N'ex_004',4),
    (N'检测部位',N'左前翼子板',   N'ex_005',5),
    (N'检测部位',N'左A柱外观',    N'ex_006',6),
    (N'检测部位',N'左前门',       N'ex_007',7),
    (N'检测部位',N'左上边梁外观', N'ex_008',8),
    (N'检测部位',N'左下边梁外观', N'ex_009',9),
    (N'检测部位',N'左后门',       N'ex_010',10),
    (N'检测部位',N'左C柱外观',    N'ex_011',11),
    (N'检测部位',N'左后翼子板',   N'ex_012',12),
    (N'检测部位',N'后盖',         N'ex_013',13),
    (N'检测部位',N'右C柱外观',    N'ex_014',14),
    (N'检测部位',N'右后翼子板',   N'ex_015',15),
    (N'检测部位',N'右后门',       N'ex_016',16),
    (N'检测部位',N'右前门',       N'ex_017',17),
    (N'检测部位',N'右上边梁外观', N'ex_018',18),
    (N'检测部位',N'右下边梁外观', N'ex_019',19),
    (N'检测部位',N'右A柱外观',    N'ex_020',20),
    (N'检测部位',N'右前翼子板',   N'ex_021',21)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'exterior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 外观 - 前部检测（12项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'前部检测',N'前雨刮臂',       N'ex_022',22),
    (N'前部检测',N'前保险杠',       N'ex_023',23),
    (N'前部检测',N'前底盘',         N'ex_024',24),
    (N'前部检测',N'前保下饰板',     N'ex_025',25),
    (N'前部检测',N'发动机下护板',   N'ex_026',26),
    (N'前部检测',N'前中网',         N'ex_027',27),
    (N'前部检测',N'左前大灯清洗器', N'ex_028',28),
    (N'前部检测',N'右前大灯清洗器', N'ex_029',29),
    (N'前部检测',N'雾灯',           N'ex_030',30),
    (N'前部检测',N'发动机及附件',   N'ex_031',31),
    (N'前部检测',N'变速箱及附件',   N'ex_032',32),
    (N'前部检测',N'蓄电池',         N'ex_033',33)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'exterior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 外观 - 后部检测（10项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'后部检测',N'后挡风玻璃',         N'ex_034',34),
    (N'后部检测',N'后雨刮臂',           N'ex_035',35),
    (N'后部检测',N'鲨鱼鳍',             N'ex_036',36),
    (N'后部检测',N'后扰流板',           N'ex_037',37),
    (N'后部检测',N'左后车灯',           N'ex_038',38),
    (N'后部检测',N'右后车灯',           N'ex_039',39),
    (N'后部检测',N'驻车影像（摄像头）', N'ex_040',40),
    (N'后部检测',N'后保险杠',           N'ex_041',41),
    (N'后部检测',N'排气管及消音器',     N'ex_042',42),
    (N'后部检测',N'后底盘',             N'ex_043',43)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'exterior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 外观 - 右部检测（13项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'右部检测',N'右后轮胎',           N'ex_044',44),
    (N'右部检测',N'右后轮毂',           N'ex_045',45),
    (N'右部检测',N'右后轮眉（塑料件）', N'ex_046',46),
    (N'右部检测',N'右后轮胎隔音罩',     N'ex_047',47),
    (N'右部检测',N'油箱盖/充电口盖',    N'ex_048',48),
    (N'右部检测',N'右后车门玻璃',       N'ex_049',49),
    (N'右部检测',N'右D柱外观',          N'ex_050',50),
    (N'右部检测',N'右前车门玻璃',       N'ex_051',51),
    (N'右部检测',N'右后视镜',           N'ex_052',52),
    (N'右部检测',N'右前轮胎',           N'ex_053',53),
    (N'右部检测',N'右前轮毂',           N'ex_054',54),
    (N'右部检测',N'右前轮眉（塑料件）', N'ex_055',55),
    (N'右部检测',N'右前轮胎隔音罩',     N'ex_056',56)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'exterior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 内饰 - 检测部位（2项）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'检测部位',N'控制台',N'in_001',1),
    (N'检测部位',N'手套箱',N'in_002',2)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'interior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- 内饰 - 机电及内饰检测（57项，分两批插入避免VALUES过长）
INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'机电及内饰检测',N'遥控钥匙',           N'in_003',3),
    (N'机电及内饰检测',N'主驾座椅',           N'in_004',4),
    (N'机电及内饰检测',N'主驾安全带',         N'in_005',5),
    (N'机电及内饰检测',N'主驾安全带锁扣',     N'in_006',6),
    (N'机电及内饰检测',N'主驾安全带调节开关', N'in_007',7),
    (N'机电及内饰检测',N'前排坐舱底板内饰',   N'in_008',8),
    (N'机电及内饰检测',N'副驾座椅',           N'in_009',9),
    (N'机电及内饰检测',N'副驾安全带',         N'in_010',10),
    (N'机电及内饰检测',N'副驾安全带卡扣',     N'in_011',11),
    (N'机电及内饰检测',N'副驾安全带锁扣',     N'in_012',12),
    (N'机电及内饰检测',N'副驾安全带调节开关', N'in_013',13),
    (N'机电及内饰检测',N'方向盘',             N'in_014',14),
    (N'机电及内饰检测',N'安全气囊',           N'in_015',15),
    (N'机电及内饰检测',N'转向机',             N'in_016',16),
    (N'机电及内饰检测',N'喇叭',               N'in_017',17),
    (N'机电及内饰检测',N'仪表盘',             N'in_018',18),
    (N'机电及内饰检测',N'音响',               N'in_019',19),
    (N'机电及内饰检测',N'中控锁',             N'in_020',20),
    (N'机电及内饰检测',N'驻车雷达',           N'in_021',21),
    (N'机电及内饰检测',N'底盘升降',           N'in_022',22),
    (N'机电及内饰检测',N'变速杆',             N'in_023',23),
    (N'机电及内饰检测',N'驻车制动装置',       N'in_024',24),
    (N'机电及内饰检测',N'中控面板',           N'in_025',25),
    (N'机电及内饰检测',N'车内灯光',           N'in_026',26),
    (N'机电及内饰检测',N'内视镜',             N'in_027',27),
    (N'机电及内饰检测',N'异味',               N'in_028',28),
    (N'机电及内饰检测',N'前排空调出风口',     N'in_029',29),
    (N'机电及内饰检测',N'前排手扶箱（含杯托）',N'in_030',30)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'interior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

INSERT INTO VOV_DealerVehicleInspectItem (CategoryID, SubCategory, Name, Code, SortNo, CreateTime)
SELECT c.ID, v.SubCategory, v.Name, v.Code, v.SortNo, GETDATE()
FROM VOV_DealerVehicleInspectCategory c
CROSS JOIN (VALUES
    (N'机电及内饰检测',N'主驾驶遮阳板',   N'in_031',31),
    (N'机电及内饰检测',N'副驾驶遮阳板',   N'in_032',32),
    (N'机电及内饰检测',N'A柱内饰',        N'in_033',33),
    (N'机电及内饰检测',N'车顶内饰',       N'in_034',34),
    (N'机电及内饰检测',N'车顶把手',       N'in_035',35),
    (N'机电及内饰检测',N'左前门内饰',     N'in_036',36),
    (N'机电及内饰检测',N'左后门内饰',     N'in_037',37),
    (N'机电及内饰检测',N'后排坐舱底板内饰',N'in_038',38),
    (N'机电及内饰检测',N'后排座椅',       N'in_039',39),
    (N'机电及内饰检测',N'左后排安全带',   N'in_040',40),
    (N'机电及内饰检测',N'中后排安全带',   N'in_041',41),
    (N'机电及内饰检测',N'右后排安全带',   N'in_042',42),
    (N'机电及内饰检测',N'左后排化妆镜',   N'in_043',43),
    (N'机电及内饰检测',N'右后排化妆镜',   N'in_044',44),
    (N'机电及内饰检测',N'后排控制面板',   N'in_045',45),
    (N'机电及内饰检测',N'后排空调出风口', N'in_046',46),
    (N'机电及内饰检测',N'后排手扶箱',     N'in_047',47),
    (N'机电及内饰检测',N'B柱内饰',        N'in_048',48),
    (N'机电及内饰检测',N'C柱内饰',        N'in_049',49),
    (N'机电及内饰检测',N'D柱内饰',        N'in_050',50),
    (N'机电及内饰检测',N'右后门内饰',     N'in_051',51),
    (N'机电及内饰检测',N'右前门内饰',     N'in_052',52),
    (N'机电及内饰检测',N'后排遮阳帘',     N'in_053',53),
    (N'机电及内饰检测',N'遮物帘/卡扣',    N'in_054',54),
    (N'机电及内饰检测',N'备胎盖板',       N'in_055',55),
    (N'机电及内饰检测',N'高位刹车灯',     N'in_056',56),
    (N'机电及内饰检测',N'天窗玻璃',       N'in_057',57),
    (N'机电及内饰检测',N'仪表台',         N'in_058',58),
    (N'机电及内饰检测',N'尾箱盖内饰板',   N'in_059',59)
) v(SubCategory,Name,Code,SortNo)
WHERE c.Code = N'interior'
  AND NOT EXISTS (SELECT 1 FROM VOV_DealerVehicleInspectItem WHERE CategoryID = c.ID AND Code = v.Code);

-- ③ 为新增检测项批量插入10个标准选项（幂等：已有选项的项跳过）
INSERT INTO VOV_DealerVehicleInspectOption (InspectItemID, Name, Code, Type, Sort, CreateTime)
SELECT i.ID, opt.Name, i.Code + N'_' + opt.Code, N'checkbox', opt.Sort, GETDATE()
FROM VOV_DealerVehicleInspectItem i
CROSS JOIN (VALUES
    (N'正常',     N'o01',1),
    (N'划痕',     N'o02',2),
    (N'凹痕',     N'o03',3),
    (N'变形',     N'o04',4),
    (N'整形',     N'o05',5),
    (N'锈蚀',     N'o06',6),
    (N'切焊',     N'o07',7),
    (N'斑点',     N'o08',8),
    (N'漆面脱落', N'o09',9),
    (N'喷漆',     N'o10',10)
) opt(Name, Code, Sort)
WHERE i.CategoryID IN (
    SELECT ID FROM VOV_DealerVehicleInspectCategory WHERE Code IN (N'skeleton',N'exterior',N'interior')
)
AND NOT EXISTS (
    SELECT 1 FROM VOV_DealerVehicleInspectOption o WHERE o.InspectItemID = i.ID
);

-- ④ 验证结果
SELECT
    c.Code,
    c.Name AS CategoryName,
    COUNT(DISTINCT i.ID) AS ItemCount,
    COUNT(o.ID) AS OptionCount
FROM VOV_DealerVehicleInspectCategory c
LEFT JOIN VOV_DealerVehicleInspectItem i ON i.CategoryID = c.ID
LEFT JOIN VOV_DealerVehicleInspectOption o ON o.InspectItemID = i.ID
WHERE c.Code IN (N'skeleton',N'exterior',N'interior')
GROUP BY c.Code, c.Name
ORDER BY c.Code;
GO

-- ============================================================
-- 存量数据修复：将已入库的乱码/问号中文字段重新写入正确值
-- 说明：
--   若 T01 曾用不带 N 前缀的字符串插入，中文字段会存为乱码或 '?'
--   本节用 N'...' 重新 UPDATE 覆盖，确保数据正确
--   幂等：重复执行无副作用
-- ============================================================

USE [PvUCM];
GO

-- 修复分类名称
UPDATE VOV_DealerVehicleInspectCategory SET Name = N'骨架' WHERE Code = N'skeleton' AND Name != N'骨架';
UPDATE VOV_DealerVehicleInspectCategory SET Name = N'外观' WHERE Code = N'exterior' AND Name != N'外观';
UPDATE VOV_DealerVehicleInspectCategory SET Name = N'内饰' WHERE Code = N'interior' AND Name != N'内饰';

-- 修复检测项名称和子分类（按 Code 精确匹配，批量 UPDATE）
-- 骨架
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'检测部位', Name=N'车顶'      WHERE Code=N'sk_001' AND (SubCategory!=N'检测部位' OR Name!=N'车顶');
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'检测部位', Name=N'水箱框架'  WHERE Code=N'sk_002' AND (SubCategory!=N'检测部位' OR Name!=N'水箱框架');
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'左前灯架-车辆支架' WHERE Code=N'sk_003' AND Name!=N'左前灯架-车辆支架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'右前灯架-车辆支架' WHERE Code=N'sk_004' AND Name!=N'右前灯架-车辆支架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'前防撞横梁'   WHERE Code=N'sk_005' AND Name!=N'前防撞横梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'左前梁头'     WHERE Code=N'sk_006' AND Name!=N'左前梁头';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'左前纵梁'     WHERE Code=N'sk_007' AND Name!=N'左前纵梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'左前翼子板内板' WHERE Code=N'sk_008' AND Name!=N'左前翼子板内板';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'左前减震器座' WHERE Code=N'sk_009' AND Name!=N'左前减震器座';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'右前梁头'     WHERE Code=N'sk_010' AND Name!=N'右前梁头';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'右前纵梁'     WHERE Code=N'sk_011' AND Name!=N'右前纵梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'右前翼子板内板' WHERE Code=N'sk_012' AND Name!=N'右前翼子板内板';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'右前减震器座' WHERE Code=N'sk_013' AND Name!=N'右前减震器座';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'前部检测', Name=N'防火墙'       WHERE Code=N'sk_014' AND Name!=N'防火墙';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左上边梁骨架'   WHERE Code=N'sk_015' AND Name!=N'左上边梁骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左下边梁'       WHERE Code=N'sk_016' AND Name!=N'左下边梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左A柱骨架'      WHERE Code=N'sk_017' AND Name!=N'左A柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左B柱骨架'      WHERE Code=N'sk_018' AND Name!=N'左B柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左C柱骨架'      WHERE Code=N'sk_019' AND Name!=N'左C柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左D柱骨架'      WHERE Code=N'sk_020' AND Name!=N'左D柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'左部检测', Name=N'左后翼子板内板' WHERE Code=N'sk_021' AND Name!=N'左后翼子板内板';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'左后灯架-车辆支架' WHERE Code=N'sk_022' AND Name!=N'左后灯架-车辆支架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'右后灯架-车辆支架' WHERE Code=N'sk_023' AND Name!=N'右后灯架-车辆支架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'后围板'               WHERE Code=N'sk_024' AND Name!=N'后围板';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'后备箱底板（备胎槽）' WHERE Code=N'sk_025' AND Name!=N'后备箱底板（备胎槽）';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'后防撞横梁'           WHERE Code=N'sk_026' AND Name!=N'后防撞横梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'左后纵梁'             WHERE Code=N'sk_027' AND Name!=N'左后纵梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'左后梁头'             WHERE Code=N'sk_028' AND Name!=N'左后梁头';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'左后减震器座'         WHERE Code=N'sk_029' AND Name!=N'左后减震器座';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'右后梁头'             WHERE Code=N'sk_030' AND Name!=N'右后梁头';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'右后纵梁'             WHERE Code=N'sk_031' AND Name!=N'右后纵梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'右后减震器座'         WHERE Code=N'sk_032' AND Name!=N'右后减震器座';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'后部检测', Name=N'后窗台板'             WHERE Code=N'sk_033' AND Name!=N'后窗台板';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右后翼子板内板' WHERE Code=N'sk_034' AND Name!=N'右后翼子板内板';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右上边梁骨架'   WHERE Code=N'sk_035' AND Name!=N'右上边梁骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右下边梁'       WHERE Code=N'sk_036' AND Name!=N'右下边梁';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右D柱骨架'      WHERE Code=N'sk_037' AND Name!=N'右D柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右C柱骨架'      WHERE Code=N'sk_038' AND Name!=N'右C柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右B柱骨架'      WHERE Code=N'sk_039' AND Name!=N'右B柱骨架';
UPDATE VOV_DealerVehicleInspectItem SET SubCategory=N'右部检测', Name=N'右A柱骨架'      WHERE Code=N'sk_040' AND Name!=N'右A柱骨架';

-- 修复选项名称（按 Code 后缀精确匹配）
UPDATE VOV_DealerVehicleInspectOption SET Name=N'正常'     WHERE Code LIKE N'%_o01' AND Name!=N'正常';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'划痕'     WHERE Code LIKE N'%_o02' AND Name!=N'划痕';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'凹痕'     WHERE Code LIKE N'%_o03' AND Name!=N'凹痕';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'变形'     WHERE Code LIKE N'%_o04' AND Name!=N'变形';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'整形'     WHERE Code LIKE N'%_o05' AND Name!=N'整形';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'锈蚀'     WHERE Code LIKE N'%_o06' AND Name!=N'锈蚀';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'切焊'     WHERE Code LIKE N'%_o07' AND Name!=N'切焊';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'斑点'     WHERE Code LIKE N'%_o08' AND Name!=N'斑点';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'漆面脱落' WHERE Code LIKE N'%_o09' AND Name!=N'漆面脱落';
UPDATE VOV_DealerVehicleInspectOption SET Name=N'喷漆'     WHERE Code LIKE N'%_o10' AND Name!=N'喷漆';

-- 验证修复结果（应全部返回正确中文，无乱码）
SELECT Code, Name FROM VOV_DealerVehicleInspectCategory WHERE Code IN (N'skeleton',N'exterior',N'interior');
SELECT Code, SubCategory, Name FROM VOV_DealerVehicleInspectItem WHERE Code IN (N'sk_001',N'sk_002',N'ex_001',N'in_001') ORDER BY Code;
SELECT Code, Name FROM VOV_DealerVehicleInspectOption WHERE Code IN (N'sk_001_o01',N'sk_001_o02',N'ex_001_o01') ORDER BY Code;
GO
