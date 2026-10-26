-- =============================================
-- T25：经销商收车检测 PC端菜单配置
-- 菜单位置：二手车 → 检测管理 → 经销商收车检测
-- 组件名：UsedcarInspectDealerInspectTaskList
-- =============================================

-- 第一步：查询"检测管理"父菜单ID（确认后再执行第二步）
SELECT ID, PID, Name, Title, Path, Component
FROM SYS_Menu
WHERE (Title LIKE N'%检测管理%' OR Name LIKE N'%inspect%')
  AND IsDeleted = 0
ORDER BY CreateTime DESC

-- =============================================
-- 第二步：插入菜单（将 @InspectParentID 替换为上面查到的检测管理菜单ID）
-- =============================================

DECLARE @InspectParentID UNIQUEIDENTIFIER

-- 自动获取"检测管理"父菜单ID
SELECT TOP 1 @InspectParentID = ID FROM SYS_Menu
WHERE (Title LIKE N'%检测管理%' OR Name LIKE N'%inspect%')
  AND IsDeleted = 0
ORDER BY CreateTime DESC

IF @InspectParentID IS NULL
BEGIN
    PRINT N'错误：未找到检测管理父菜单，请手动设置 @InspectParentID'
END
ELSE
BEGIN
    PRINT N'检测管理父菜单ID：' + CAST(@InspectParentID AS NVARCHAR(50))

    IF NOT EXISTS (
        SELECT 1 FROM SYS_Menu
        WHERE Name = N'usedcar-inspect-dealer-task-list' AND IsDeleted = 0
    )
    BEGIN
        INSERT INTO SYS_Menu (
            ID, Name, Path, Title, Component, Icon, Sort,
            PID, CreateTime, UpdateTime, IsDeleted
        )
        VALUES (
            NEWID(),
            N'usedcar-inspect-dealer-task-list',
            N'/usedcar/inspect/dealerInspectTaskList',
            N'经销商收车检测',
            N'UsedcarInspectDealerInspectTaskList',
            N'file-search',
            100,
            @InspectParentID,
            GETDATE(),
            GETDATE(),
            0
        )
        PRINT N'菜单 [经销商收车检测] 创建成功'
    END
    ELSE
    BEGIN
        PRINT N'菜单 [经销商收车检测] 已存在，跳过'
    END
END

-- =============================================
-- 第三步：验证
-- =============================================
SELECT ID, PID, Name, Title, Path, Component, Sort
FROM SYS_Menu
WHERE Name = N'usedcar-inspect-dealer-task-list' AND IsDeleted = 0
