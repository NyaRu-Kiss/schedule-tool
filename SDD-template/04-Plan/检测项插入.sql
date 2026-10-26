
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
