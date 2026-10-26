# 经销商收车检测模块 — SDD 开发任务清单

> **参考文档**  
> - 需求：`d:\Projects\ProjectV\企微检测\文档\经销商收车检测模块-PRD.md`  
> - 技术方案：`d:\Projects\ProjectV\企微检测\文档\技术方案_经销商收车检测模块_V2.md`  
> - 设计图目录：`d:\Projects\ProjectV\企微检测\设计图\`  
> - 检测报告设计稿（HTML）：`d:\Projects\ProjectV\企微检测\检测报告\检测报告.html`

## 标识说明

| 标识 | 含义 |
|------|------|
| `[P]` | **可并行** — 同阶段内可与其他 `[P]` 任务同时开始 |
| `[S→Txx]` | **串行** — 须在 Txx 完成后才能开始 |
| `[ ]` | 待开始 |

**SDD 六步法**每个 Task 包含：① 需求说明 → ② 接口定义 → ③ 数据模型 → ④ 业务逻辑 → ⑤ 前端实现 → ⑥ 验证标准

---

---

# 阶段 0：数据库建表 ⚠️ 所有任务前置条件

---

## T00 建表及索引创建 `[S]`

### ① 需求说明
PRD 3.1 ~ 3.7 全部功能的数据持久层。新建独立业务表 `VOV_DealerVehicleInspectTask`，存储检测任务的全生命周期数据；检测项字典表（Category/Item/Option）沿用现有结构。

### ② 接口定义
无接口，纯 DDL。

### ③ 数据模型
执行 `技术方案_V2.md § 3.建表` 中的完整 SQL，字段说明如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| ID | INT IDENTITY PK | 主键 |
| InspectCode | NVARCHAR(50) | 任务编号，格式 INSP{yyyyMMdd}{D3} |
| Source | NVARCHAR(20) DEFAULT 'MANUAL' | 来源：LTO / MANUAL |
| LtoTaskId | NVARCHAR(100) NULL | LTO任务ID，Source=LTO时填入 |
| DealerCode | NVARCHAR(50) NOT NULL | 经销商代码 |
| VehicleModelId | NVARCHAR(50) NULL | 车型ID，关联品牌车型表 |
| CarSeries | NVARCHAR(50) NULL | 车系，用于企微端筛选 |
| Vin | NVARCHAR(20) NULL | 车架号 |
| PlateNumber | NVARCHAR(20) NULL | 车牌号码 |
| BodyColor | NVARCHAR(20) NULL | 车身颜色 |
| Mileage | NVARCHAR(20) NULL | 表显里程 |
| Owner | NVARCHAR(50) NULL | 所有人 |
| OwnerType | NVARCHAR(20) NULL | 所有人性质：个人/企业/单位 |
| UseType | NVARCHAR(20) NULL | 使用性质：非营运/营运/出租/教练 |
| FactoryDate | NVARCHAR(20) NULL | 出厂日期，格式 YYYY-MM |
| FirstLicenseDate | NVARCHAR(20) NULL | 首次上牌日期，格式 YYYY-MM-DD |
| InspectUserId | INT NOT NULL DEFAULT 0 | 检测人账号ID |
| InspectUserName | NVARCHAR(50) NULL | 检测人姓名，默认评估师名称 |
| DrivingLicensePhoto | NTEXT NULL | 行驶证照片URL |
| CustomerName | NVARCHAR(50) NULL | 联系人姓名 |
| CustomerPhone | NVARCHAR(20) NULL | 联系手机号，客户验证时比对 |
| ExteriorPhotos | NTEXT NULL | 外观照片 JSON `{"车辆正前":"url","发动机":"url","车辆左侧":"url","车辆后侧":"url","后备箱":"url"}` |
| InteriorPhotos | NTEXT NULL | 内饰照片 JSON `{"主驾驶座椅":"url","仪表盘":"url","后排左":"url","仪表台":"url"}` |
| VinKeyPhotos | NTEXT NULL | 车架号照片 JSON `{"车架号":"url"}` |
| VehicleDocPhotos | NTEXT NULL | 手续照片 JSON `{"登记证":"url","交强险保单":"url"}` |
| IsBurned | BIT NOT NULL DEFAULT 0 | 是否火烧 |
| BurnedPhotos | NTEXT NULL | 火烧照片 JSON Array `["url1","url2","url3"]`，最多3张 |
| IsFlooded | BIT NOT NULL DEFAULT 0 | 是否水淹 |
| FloodedPhotos | NTEXT NULL | 水淹照片 JSON Array，最多3张 |
| IsFrameAccident | BIT NOT NULL DEFAULT 0 | 是否车架事故（PRD中称"结构损伤"） |
| FrameAccidentPhotos | NTEXT NULL | 车架事故照片 JSON Array，最多3张 |
| InspectData | NTEXT NULL | 车辆检测数据 JSON Array（骨架/外观/内饰检测选项结果） |
| PaintThicknessData | NTEXT NULL | 漆面厚度 JSON Array `[{"name":"前盖","value":135},...]`，共17项 |
| IsPriceNegotiable | BIT NOT NULL DEFAULT 0 | 是否价格面议 |
| EstimatedPrice | DECIMAL(18,2) NULL | 车辆评估价格，面议时为NULL |
| TotalTransactionPrice | DECIMAL(18,2) NULL | 本次交易总价，面议时为NULL |
| ResidualValueAmount | DECIMAL(18,2) NULL | 残值保障金金额 |
| SubsidyAmount | DECIMAL(18,2) NULL | 国补/区补等其他补贴 |
| ReportStatus | INT NOT NULL DEFAULT 0 | -1=作废 0=草稿 1=已生成 2=已发送 3=已查看 |
| ReportToken | NVARCHAR(100) NULL | 32位无连字符GUID，报告分享链接Token |
| IsViewed | BIT NOT NULL DEFAULT 0 | 客户是否已查看 |
| InspectTime | DATETIME NULL | 检测完成时间（生成报告时写入） |
| ViewedTime | DATETIME NULL | 客户查看时间 |
| SmsCode | NVARCHAR(10) NULL | 短信验证码（临时存储，验证后清空） |
| SmsCodeExpire | DATETIME NULL | 验证码过期时间（5分钟） |
| CreateTime | DATETIME NOT NULL DEFAULT GETDATE() | 创建时间 |
| UpdateTime | DATETIME NULL | 最后更新时间 |

索引：
- `UNIQUE INDEX IX_InspectTask_ReportToken ON (ReportToken) WHERE ReportToken IS NOT NULL`
- `INDEX IX_InspectTask_DealerCode_CreateTime ON (DealerCode, CreateTime DESC)`
- `INDEX IX_InspectTask_Status_CreateTime ON (ReportStatus, CreateTime DESC)`

### ④ 业务逻辑
1. 在 PvUCM 数据库执行建表 SQL
2. 执行三个 CREATE INDEX 语句

### ⑤ 前端实现
无。

### ⑥ 验证标准
- [ ] `SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='VOV_DealerVehicleInspectTask'` 有结果
- [ ] `SELECT * FROM INFORMATION_SCHEMA.INDEXES WHERE TABLE_NAME='VOV_DealerVehicleInspectTask'` 显示3个索引

---

---

# 阶段 1：后端接口实现（T00 完成后）

---

## T01 检测项字典数据初始化 `[P]`

### ① 需求说明
PRD 3.3 车辆检测 → 检测项清单。骨架/外观/内饰三大类，共约155个检测部位，每个部位有多个检测选项（划痕/凹痕/变形/整形/锈蚀/切焊/斑点/漆面脱落/喷漆）。数据存入已有的 `VOV_DealerVehicleInspectCategory`、`VOV_DealerVehicleInspectItem`、`VOV_DealerVehicleInspectOption` 三张字典表。

### ② 接口定义
无（数据初始化，无接口），后续前端通过 `GET /api/VehicleInspect/GetInspectCategories?inspectId=` 读取。

### ③ 数据模型

**VOV_DealerVehicleInspectCategory**（3条）

| Code | Name |
|------|------|
| skeleton | 骨架 |
| exterior | 外观 |
| interior | 内饰 |

**VOV_DealerVehicleInspectItem**（按 PRD 检测项清单，示例）

| CategoryID | SubCategory | Name | SortNo |
|-----------|-------------|------|--------|
| 骨架ID | 检测部位 | 车顶 | 1 |
| 骨架ID | 检测部位 | 水箱框架 | 2 |
| 骨架ID | 前部检测 | 左前灯架-车辆支架 | 3 |
| ... | ... | ... | ... |
| 外观ID | 检测部位 | 前挡风玻璃 | 1 |
| ... | 共56个外观检测项 | ... | ... |
| 内饰ID | 检测部位 | 控制台 | 1 |
| ... | 共59个内饰检测项 | ... | ... |

**VOV_DealerVehicleInspectOption**（每个检测项约7~9个选项）

| InspectItemID | Name | Type | Sort |
|--------------|------|------|------|
| 任意部位ID | 正常 | checkbox | 1 |
| 任意部位ID | 划痕 | checkbox | 2 |
| 任意部位ID | 凹痕 | checkbox | 3 |
| 任意部位ID | 变形 | checkbox | 4 |
| 任意部位ID | 整形 | checkbox | 5 |
| 任意部位ID | 锈蚀 | checkbox | 6 |
| 任意部位ID | 切焊 | checkbox | 7 |
| 任意部位ID | 斑点 | checkbox | 8 |
| 任意部位ID | 漆面脱落 | checkbox | 9 |
| 任意部位ID | 喷漆 | checkbox | 10 |

### ④ 业务逻辑
1. 编写批量 INSERT 脚本，按 PRD § 三、3.3.3 的检测项清单逐一插入
2. 注意 SubCategory 字段区分二级分组（前部/左部/后部/右部检测等）
3. SortNo 按 PRD 表格顺序编号

### ⑤ 前端实现
无（数据层初始化）。

### ⑥ 验证标准
- [ ] `SELECT COUNT(*) FROM VOV_DealerVehicleInspectCategory` = 3
- [ ] `SELECT COUNT(*) FROM VOV_DealerVehicleInspectItem` ≥ 150（骨架40+外观56+内饰59）
- [ ] `SELECT COUNT(*) FROM VOV_DealerVehicleInspectOption` ≥ 1000
- [ ] 前端 Step3 骨架检查 Tab 能加载出检测项列表

---

## T02 后端接口：LTO 下发检测任务 `[P]`

### ① 需求说明
PRD 3.1 LTO下发：评估师在 LTO 点击【车辆检测】，LTO 系统通过接口推送任务到 NBMS。同一 VIN 允许重复提交（不作废历史任务）。接口在 `VehicleInspectController.cs` 中已有代码骨架，需验证并补全认证逻辑。

### ② 接口定义

```
POST /api/VehicleInspect/ReceiveLtoTask
Content-Type: application/json
[AllowAnonymous] （认证方式待与LTO确认，暂留空）

Request Body（ReceiveLtoTaskIm）:
{
  "LtoTaskId": "string",       // LTO任务ID，必填
  "Vin": "string",             // 车架号，必填
  "VehicleModelId": "string",  // 车型ID
  "CarSeries": "string",       // 车系
  "BodyColor": "string",       // 车身颜色
  "Owner": "string",           // 所有人
  "OwnerType": "string",       // 所有人性质
  "FirstLicenseDate": "string",// 首次上牌日期
  "EvaluatorId": int,          // 评估师账号ID
  "EvaluatorName": "string",   // 评估师姓名
  "CustomerName": "string",    // 联系人姓名
  "CustomerPhone": "string",   // 联系人手机号
  "DealerCode": "string"       // 经销商代码，必填
}

Response（Code="0"）:
{
  "Code": "0",
  "Message": "操作成功",
  "Data": {
    "InspectCode": "INSP20260526001",
    "ID": 123
  }
}
```

### ③ 数据模型
写入 `VOV_DealerVehicleInspectTask`：
- `Source = 'LTO'`，`ReportStatus = 0`，`LtoTaskId = 入参LtoTaskId`
- `InspectCode = 'INSP' + yyyyMMdd + 当日序号(D3)`（查当日最大序号 +1）
- `InspectUserId = 入参EvaluatorId`，`InspectUserName = 入参EvaluatorName`
- LTO传输字段（Is=是的列）：VehicleModelId/CarSeries/Vin/BodyColor/Owner/OwnerType/FirstLicenseDate/CustomerName/CustomerPhone/DealerCode

### ④ 业务逻辑
```
1. 参数校验：Vin 和 DealerCode 不能为空
2. 生成 InspectCode：
   today = DateTime.Today
   todayCount = SELECT COUNT(*) WHERE CreateTime >= today AND CreateTime < today+1
   inspectCode = "INSP" + today.ToString("yyyyMMdd") + (todayCount+1).ToString("D3")
3. INSERT VOV_DealerVehicleInspectTask，写入所有LTO传输字段
4. 返回 { InspectCode, ID }
```

### ⑤ 前端实现
无（LTO系统直接调用后端接口）。

### ⑥ 验证标准
- [ ] Postman POST 接口，响应 Code="0"，Data.InspectCode 格式正确
- [ ] 数据库中新增一条记录，Source='LTO'，ReportStatus=0
- [ ] 同一 VIN 连续提交两次，两条记录均存在（不作废）
- [ ] Vin 为空时返回错误提示

---

## T03 后端接口：检测任务列表（企微端）`[P]`

### ① 需求说明
PRD 3.2 检测任务列表（企微）：评估师/经理在企微端查看本经销商的检测任务列表，支持 VIN/车系/时间/状态筛选，创建时间降序，分页返回。

### ② 接口定义

```
GET /api/VehicleInspect/GetInspectTaskList
[Authenticate]

Query Parameters:
  Vin: string?           // VIN模糊查询
  CarSeries: string?     // 车系精确查询
  Status: int?           // 前端传参：0=进行中 1=待查看 3=已查看
  StartDate: string?     // 创建时间起始 YYYY-MM-DD
  EndDate: string?       // 创建时间截止 YYYY-MM-DD（含当天）
  Page: string           // JSON: {"Index":1,"Size":20}

Response（Code="0"）:
{
  "Code": "0",
  "Data": [
    {
      "ID": 123,
      "InspectCode": "INSP20260526001",
      "Vin": "LVYPDM1D1SP133126",
      "CarSeries": "XC60",
      "ReportStatus": 0,      // 0/1/2/3
      "CreateTime": "2026-05-26T10:30:00"
    }
  ],
  "DataTotal": 42
}
```

**前端 Status 参数 → 后端 ReportStatus 映射**：
- 前端 Status=0 → WHERE ReportStatus=0
- 前端 Status=1 → WHERE ReportStatus IN (1,2)（待查看包含已发送）
- 前端 Status=3 → WHERE ReportStatus=3

### ③ 数据模型
查询 `VOV_DealerVehicleInspectTask`：
- 必须 WHERE DealerCode = 当前登录用户的经销商代码
- 排除 ReportStatus = -1（已作废）
- 创建时间降序 ORDER BY CreateTime DESC

### ④ 业务逻辑
```
1. 获取当前用户 DealerCode：MyIdentity.AccountDetailInfo.Code
2. 反序列化 Page 参数得到 PageIndex/PageSize
3. 构建查询条件（动态WHERE）：
   - WHERE DealerCode = dealerCode AND ReportStatus != -1
   - IF Vin ≠ null: AND Vin LIKE '%' + Vin + '%'
   - IF CarSeries ≠ null: AND CarSeries = CarSeries
   - IF Status == 0: AND ReportStatus = 0
   - IF Status == 1: AND ReportStatus IN (1,2)
   - IF Status == 3: AND ReportStatus = 3
   - IF StartDate ≠ null: AND CreateTime >= StartDate
   - IF EndDate ≠ null: AND CreateTime < EndDate.AddDays(1)
4. SELECT COUNT(*) 得到 DataTotal
5. ORDER BY CreateTime DESC, SKIP/TAKE 得到当页数据
6. 返回 { Data, DataTotal }
```

### ⑤ 前端实现
- 文件：`src/pages/inspect-task-list/index.tsx`
- 设计图：`3.2-列表-3.png`（卡片样式）、`3.2-列表-2.png`（二手车菜单）
- 搜索框：上方 VIN 搜索 + 下方三个筛选 chip（旧车车系/单据创建时间/状态）
- 状态chip激活时显示蓝色背景，点击弹出选项菜单
- 卡片：InspectCode（标题）+ 状态标签（右上角）+ VIN 行 + 创建时间行
- 状态标签颜色：进行中=蓝(#1890FF)，待查看=橙(#FA8C16)，已查看=绿(#52C41A)

### ⑥ 验证标准
- [ ] 不带参数请求，返回当前登录经销商的任务列表
- [ ] 传入不存在的经销商的 VIN，返回空列表（DealerCode 隔离）
- [ ] Status=1 时，ReportStatus=1 和 ReportStatus=2 的任务均返回
- [ ] 翻页正确，DataTotal 与实际数量一致
- [ ] 前端列表卡片状态标签颜色正确

---

## T04 后端接口：检测任务详情 `[P]`

### ① 需求说明
评估师从列表进入某个检测任务后，前端需要获取该任务的所有已填写数据，各步骤表单回显。

### ② 接口定义

```
GET /api/VehicleInspect/GetInspectTaskDetail
[Authenticate]
?inspectId=123

Response（Code="0"）:
{
  "Code": "0",
  "Data": {  // InspectTaskDetailVm
    "ID": 123,
    "InspectCode": "INSP20260526001",
    "ReportStatus": 0,
    "Source": "LTO",          // LTO或MANUAL，前端据此决定VIN是否只读
    "VehicleModelId": "xxx",
    "CarSeries": "XC60",
    "Vin": "LVYP...",
    "PlateNumber": "浙G2R20F",
    "BodyColor": "白色",
    "Mileage": "3.2",
    "Owner": "张智勇",
    "OwnerType": "个人",
    "UseType": "非营运",
    "FactoryDate": "2024-07",
    "FirstLicenseDate": "2024-07-05",
    "InspectUserName": "张三",
    "DrivingLicensePhoto": "https://...",
    "CustomerName": "张智勇",
    "CustomerPhone": "15705181299",
    "ExteriorPhotos": "{\"车辆正前\":\"url\",...}",
    "InteriorPhotos": "{\"主驾驶座椅\":\"url\",...}",
    "VinKeyPhotos": "{\"车架号\":\"url\"}",
    "VehicleDocPhotos": "{}",
    "IsBurned": false,
    "BurnedPhotos": "[]",
    "IsFlooded": false,
    "FloodedPhotos": "[]",
    "IsFrameAccident": false,
    "FrameAccidentPhotos": "[]",
    "InspectData": "[...]",
    "PaintThicknessData": "[{\"name\":\"前盖\",\"value\":135},...]",
    "IsPriceNegotiable": false,
    "EstimatedPrice": null,
    "TotalTransactionPrice": null,
    "ResidualValueAmount": null,
    "SubsidyAmount": null,
    "CreateTime": "2026-05-26T10:30:00"
  }
}
```

### ③ 数据模型
单表查询 `VOV_DealerVehicleInspectTask WHERE ID = inspectId AND DealerCode = 当前用户DealerCode`。

### ④ 业务逻辑
```
1. 获取当前用户 DealerCode
2. SELECT * FROM VOV_DealerVehicleInspectTask WHERE ID = inspectId AND DealerCode = dealerCode
3. 若记录不存在 → 返回 Error("检测任务不存在或无权限")
4. 映射到 InspectTaskDetailVm 返回（所有字段直传，不做转换）
```

### ⑤ 前端实现
Step1-4 全部在 `onMounted` 时调用此接口回显数据。关键逻辑：
- `Source === 'LTO'` → Step1 中 VIN 字段设为 `readonly`，显示灰色不可编辑
- `Source === 'MANUAL'` → VIN 正常可编辑

### ⑥ 验证标准
- [ ] 用已有任务 ID 请求，返回完整数据
- [ ] 用其他经销商任务 ID 请求，返回错误
- [ ] LTO任务 Source 字段为 "LTO"，前端 VIN 字段只读

---

## T05 后端接口：保存检测任务（四步表单） `[S→T02]`

### ① 需求说明
PRD 3.3 全四步表单均通过此接口保存。新增（手动创建）和修改（继续填写）使用同一接口，通过 ID 是否存在来区分。已生成报告（ReportStatus≥1）不允许修改。

### ② 接口定义

```
POST /api/VehicleInspect/SaveInspectTask
[Authenticate]
Content-Type: application/json

Request Body（SaveInspectTaskIm）—— 所有字段均可选，只传需要更新的字段：
{
  "ID": 123,                      // null=新增(MANUAL), 有值=修改
  // Step1 基本信息
  "VehicleModelId": "xxx",
  "CarSeries": "XC60",
  "Vin": "LVYP...",               // Source=LTO时忽略此字段
  "PlateNumber": "浙G2R20F",
  "BodyColor": "白色",
  "Mileage": "3.2",
  "Owner": "张智勇",
  "OwnerType": "个人",             // 个人/企业/单位
  "UseType": "非营运",             // 非营运/营运/出租/教练
  "FactoryDate": "2024-07",
  "FirstLicenseDate": "2024-07-05",
  "InspectUserName": "张三",
  "DrivingLicensePhoto": "https://...",
  "CustomerName": "张智勇",
  "CustomerPhone": "15705181299",
  // Step2 基本照片
  "ExteriorPhotos": "{\"车辆正前\":\"url\",\"发动机\":\"url\",\"车辆左侧\":\"url\",\"车辆后侧\":\"url\",\"后备箱\":\"url\"}",
  "InteriorPhotos": "{\"主驾驶座椅\":\"url\",\"仪表盘\":\"url\",\"后排左\":\"url\",\"仪表台\":\"url\"}",
  "VinKeyPhotos": "{\"车架号\":\"url\"}",
  "VehicleDocPhotos": "{\"登记证\":\"url\"}",
  "IsBurned": true,
  "BurnedPhotos": "[\"url1\",\"url2\"]",  // 最多3张
  "IsFlooded": false,
  "FloodedPhotos": "[]",
  "IsFrameAccident": false,
  "FrameAccidentPhotos": "[]",
  // Step3 车辆检测
  "InspectData": "[{\"CategoryId\":1,\"InspectItemId\":5,\"Id\":12,\"IsCheck\":true,\"Images\":[\"url\"],\"InputValue\":\"\"}]",
  "PaintThicknessData": "[{\"name\":\"前盖\",\"value\":135},{\"name\":\"左前翼子板\",\"value\":128},...]",
  // Step4 评估价格
  "IsPriceNegotiable": false,
  "EstimatedPrice": 180000.00,
  "TotalTransactionPrice": 195000.00,
  "ResidualValueAmount": 15000.00,
  "SubsidyAmount": 0
}

Response（Code="0"）:
{
  "Code": "0",
  "Data": { "ID": 123 }
}
```

### ③ 数据模型
写入/更新 `VOV_DealerVehicleInspectTask`，需要特别处理：
- `Source='LTO'` 时：UPDATE 时忽略入参的 Vin 字段（不覆盖原值）
- `Source='MANUAL'` 时：INSERT 时 Vin 必填校验
- 照片类字段（ExteriorPhotos等）：只更新有传值的字段，null不更新

### ④ 业务逻辑
```
1. 参数校验
2. 获取当前用户 DealerCode、UserId

【新增分支：ID=null 或 ID=0】
3. 校验 Vin 不为空（手动创建必填）
4. 生成 InspectCode（同T02逻辑）
5. INSERT VOV_DealerVehicleInspectTask（Source='MANUAL', ReportStatus=0）
6. 返回 { ID }

【修改分支：ID有值】
7. SELECT WHERE ID=入参ID AND DealerCode=dealerCode
8. 若不存在 → Error("任务不存在或无权限")
9. 若 ReportStatus >= 1 → Error("已生成报告的检测任务不允许修改")
10. Source='LTO'时：ApplyInput中跳过Vin字段赋值
11. 对所有非null入参字段更新到实体（null字段保留原值）
12. 重点检测照片校验：BurnedPhotos/FloodedPhotos/FrameAccidentPhotos 反序列化后数组长度不超过3
13. UPDATE，写入 UpdateTime=Now
14. 返回 { ID }
```

### ⑤ 前端实现
每步骤"下一步"按钮点击时调用此接口（先保存再跳转）。"保存"按钮仅保存不跳转。
- Step1调用时传 Step1 相关字段
- Step2调用时传照片相关字段
- Step3调用时传 InspectData + PaintThicknessData
- Step4调用时传评估价格相关字段

### ⑥ 验证标准
- [ ] 新增：ID为null，VIN有值 → 创建成功，返回新ID
- [ ] 新增：ID为null，VIN为空 → 返回错误"车架号不能为空"
- [ ] 修改LTO任务：传入Vin字段 → 原Vin不变
- [ ] ReportStatus=1的任务修改 → 返回错误
- [ ] BurnedPhotos传4张URL → 返回错误
- [ ] 分步保存：Step1保存后，Step2保存时已有Step1数据不丢失

---

## T06 后端接口：行驶证 OCR 识别 `[P]`

### ① 需求说明
PRD 3.3.1：评估师上传行驶证照片后，系统自动识别车辆信息并回填表单。OCR 识别后字段均可手动修改。识别失败不阻塞流程。

### ② 接口定义

```
POST /api/VehicleInspect/RecognizeDrivingLicense
[Authenticate]
Content-Type: application/json

Request Body:
{
  "ImageUrl": "https://oss.../driving-license.jpg"
}

Response（Code="0"）:
{
  "Code": "0",
  "Data": {  // OcrResultVm，字段均可能为null（OCR未识别到）
    "Owner": "张智勇",
    "PlateNumber": "浙G2R20F",
    "UseType": "非营运",
    "VehicleModelId": "xxx",   // 模糊匹配 DealerCarModel 表后的车型ID
    "VehicleModelName": "2024款 沃尔沃XC60 B5 四驱智雅豪华版",
    "FactoryDate": "2024-07",
    "FirstLicenseDate": "2024-07-05",
    "Vin": "LVYPDM1D1SP133126"  // 部分行驶证有VIN
  }
}
```

### ③ 数据模型
读取 `DealerCarModel` 表进行车型模糊匹配。不写入数据库（纯识别返回）。

### ④ 业务逻辑
```
1. 确认 OCR 服务：复用 ProjectVUCM.Common.OCrHelper（需确认支持行驶证识别）
2. 调用 OCR 服务，传入 ImageUrl
3. 解析 OCR 返回结果，提取字段
4. 若识别到车型文字 → 在 DealerCarModel 中模糊查询 LIKE 获取 VehicleModelId
5. 任何字段识别失败 → 该字段为 null，不影响其他字段
6. OCR服务整体失败 → 返回所有字段为null的空对象，不抛异常（Code="0"）
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-1-basic-info/index.tsx`  
设计图：`3.3.1-基本信息.png`（行驶证区块显示已上传的照片）

- 上传行驶证照片成功后，自动调用此接口
- 接口返回后：有值的字段回填到对应表单控件（可被用户修改）
- 若返回全空 → Toast提示"OCR识别失败，请手动填写"

### ⑥ 验证标准
- [ ] 上传真实行驶证图片，Owner/PlateNumber/UseType 等字段自动回填
- [ ] OCR服务异常时，返回Code="0"，Data字段均为null
- [ ] 回填后用户修改字段，修改值正常保存（不被OCR覆盖）

---

## T07 后端接口：获取检测分类（GetInspectCategories）`[S→T01]`

### ① 需求说明
前端 Step3 车辆检测页面通过此接口获取骨架/外观/内饰三大分类及其检测项，同时回填该任务已有的检测结果（从 InspectData JSON 反序列化）。

### ② 接口定义

```
GET /api/VehicleInspect/GetInspectCategories
[Authenticate]
?inspectId=123

Response（Code="0"）:
{
  "Code": "0",
  "Data": {
    "InspectCategories": [
      {
        "ID": 1,
        "Code": "skeleton",
        "Name": "骨架",
        "InspectItems": [
          {
            "Id": 1,
            "CategoryId": 1,
            "Name": "车顶",
            "Code": "skeleton_001",
            "InspectOptions": [
              {
                "Id": 1,
                "InspectItemId": 1,
                "CategoryId": 1,
                "Name": "正常",
                "Code": "opt_001",
                "Type": "checkbox",
                "Unit": null,
                "IsCheck": false,     // 从InspectData回填
                "InputValue": "",     // 从InspectData回填
                "Images": []          // 从InspectData回填
              },
              { "Name": "划痕", "IsCheck": true, "Images": ["url1"] },  // 已勾选示例
              ...
            ]
          }
        ]
      },
      { "Code": "exterior", "Name": "外观", ... },
      { "Code": "interior", "Name": "内饰", ... }
    ]
  }
}
```

### ③ 数据模型
- 读取字典表：`VOV_DealerVehicleInspectCategory` → `VOV_DealerVehicleInspectItem` → `VOV_DealerVehicleInspectOption`
- 读取任务表：`VOV_DealerVehicleInspectTask.InspectData`（JSON 反序列化后按 Id 匹配回填到选项中）

### ④ 业务逻辑
```
1. 查询三张字典表，构建完整的分类树结构
2. 查询 VOV_DealerVehicleInspectTask.InspectData WHERE ID=inspectId AND DealerCode=dealerCode
3. 反序列化 InspectData 为 List<InspectOptionVm>（包含Id/IsCheck/InputValue/Images）
4. 将 InspectData 中的选项结果按 Option.Id 匹配回填到分类树的对应选项节点上
5. 返回完整的带结果的分类树
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-3-key-inspect/index.tsx`  
设计图：`3.3.3-车辆检测-1.png`（左侧Sidebar+右侧检测项）

- `onMounted` 并发调用 `getInspectTaskDetail` 和 `getInspectCategories`
- 分类树数据传给 `vehicleDetectionStore` 供 `VehicleDetectionFormPage` 使用

### ⑥ 验证标准
- [ ] 返回数据包含骨架/外观/内饰三大类
- [ ] 骨架有40个检测项，外观有56个，内饰有59个
- [ ] 已检测过的任务：IsCheck/InputValue/Images 有正确回填
- [ ] 新任务：所有选项 IsCheck=false，Images=[]

---

## T08 后端接口：检测报告预览 `[S→T05]`

### ① 需求说明
PRD 3.4.1：评估师在 Step4 评估价格页点击【检测报告预览】，先保存当前填写的评估价格，再调用此接口获取报告数据渲染预览。预览页不发送企微/短信。

### ② 接口定义

```
GET /api/VehicleInspect/PreviewReport
[Authenticate]
?inspectId=123

Response（Code="0"）:
{
  "Code": "0",
  "Data": {  // ReportDataVm（与GetReportData返回结构相同，见T11）
    ...
  }
}
```

`ReportDataVm` 结构详见 T11。

### ③ 数据模型
只读，不修改任何状态。查询 `VOV_DealerVehicleInspectTask WHERE ID=inspectId AND DealerCode=dealerCode`。

### ④ 业务逻辑
```
1. 查询任务记录，校验 DealerCode
2. 不更新任何状态
3. 构建 ReportDataVm（同 T11 BuildReportData 方法）
4. 返回 ReportDataVm
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-4-vehicle-inspect/index.tsx`  
设计图：`3.4-评估价格-进行中.png`（预览按钮）

- 点击【检测报告预览】：先调用 `saveInspectTask` 保存当前价格数据，再调用 `previewReport`
- 返回数据后弹出底部弹层或新路由展示报告预览（无发送功能）

### ⑥ 验证标准
- [ ] 调用前后，数据库 ReportStatus 不变
- [ ] 返回数据包含正确的评估价格和检测数据
- [ ] 前端点击预览按钮后，价格数据先保存再预览

---

## T09 后端接口：生成检测报告 `[S→T05]`

### ① 需求说明
PRD 3.4.2：评估师确认生成报告后，系统生成唯一 Token，更新状态，并推送企微任务（降级短信）。

### ② 接口定义

```
POST /api/VehicleInspect/GenerateReport
[Authenticate]
Content-Type: application/json

Request Body:
{ "ID": 123 }

Response（Code="0"）:
{
  "Code": "0",
  "Data": {
    "ReportUrl": "https://h5.nbms.com/inspect-report/abc123",
    "Token": "abc123def456..."
  }
}
```

### ③ 数据模型
更新 `VOV_DealerVehicleInspectTask`：
- `ReportToken = Guid.NewGuid().ToString("N")` （32位）
- `ReportStatus = 1`（已生成）
- `InspectTime = DateTime.Now`
- 发送成功后：`ReportStatus = 2`（已发送）

### ④ 业务逻辑
```
1. 查询任务，校验 DealerCode
2. 生成 token = Guid.NewGuid().ToString("N")
3. UPDATE ReportToken=token, ReportStatus=1, InspectTime=Now
4. 拼接报告URL：ConfigHelper.GetValue("H5BaseUrl") + "/inspect-report/" + token

【企微发送尝试】
5. 调用企微查群接口（根据Vin + DealerCode），查询官方保客群
6. IF 有群 AND 评估师已加群:
   调用群SOP任务接口（templateId, groupId, evaluatorUserId, reportUrl）
   成功 → UPDATE ReportStatus=2, 返回 {ReportUrl, Token}
7. ELSE（无群/未加群/企微调用失败）:
   降级调用短信接口（CustomerPhone, reportUrl）
   UPDATE ReportStatus=2
   返回 {ReportUrl, Token}

注：步骤5~7任何异常均捕获记录日志，不影响主流程返回
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-4-vehicle-inspect/index.tsx`  
设计图：`3.4-评估价格-进行中.png`（生成按钮）、`3.4.2-生成报告.png`（确认弹框）

- 点击【生成检测报告】：弹出 Dialog 确认框，消息：`您的姓名（${InspectUserName}）将作为检测师签名展示在报告中，确认生成？`
- 确认后：先调用 `saveInspectTask` 保存价格，再调用 `generateReport`
- 成功后：Dialog 展示报告 URL 和"复制链接"按钮，页面更新状态为"待查看"，底部按钮变为仅"检测报告预览"

### ⑥ 验证标准
- [ ] 调用后 ReportToken 有值（32位无连字符），ReportStatus=2
- [ ] ReportUrl 格式正确，包含 Token
- [ ] 企微可用时：评估师企微收到任务推送
- [ ] 企微不可用时：客户手机收到短信（待T13/T14联调）
- [ ] 前端确认弹框显示正确的检测师姓名

---

## T10 后端接口：发送短信验证码 `[P]`

### ① 需求说明
PRD 3.6：客户打开报告链接后，需要输入手机号和验证码验证身份。此接口发送验证码短信，仅允许与任务 CustomerPhone 匹配的手机号请求。

### ② 接口定义

```
POST /api/DealerInspectReport/SendSmsCode
[AllowAnonymous]
Content-Type: application/json

Request Body:
{
  "Token": "abc123...",
  "Phone": "15705181299"
}

Response（Code="0"）:
{ "Code": "0", "Message": "验证码已发送" }

Error:
{ "Code": "-1", "Message": "手机号与检测任务不匹配" }
{ "Code": "-1", "Message": "报告不存在" }
```

### ③ 数据模型
查询 `VOV_DealerVehicleInspectTask WHERE ReportToken=token`，更新：
- `SmsCode`：6位随机数字
- `SmsCodeExpire`：当前时间 +5分钟

### ④ 业务逻辑
```
1. 查询 WHERE ReportToken=Token，不存在 → Error("报告不存在")
2. 校验 Phone == task.CustomerPhone，不等 → Error("手机号与检测任务不匹配")
3. 生成验证码：new Random().Next(100000, 999999).ToString()
4. UPDATE SmsCode=code, SmsCodeExpire=Now+5min
5. 发送短信（TODO：短信内容待业务提供，格式："您的检测报告验证码为：{code}，5分钟内有效，请勿泄露。"）
6. 返回成功
```

### ⑤ 前端实现
文件：`src/pages/inspect-report/verify/index.tsx`  
设计图：`3.6-客户验证.png`

- 点击"发送验证码"：校验手机号格式（11位手机号）后调用此接口
- 成功后启动60秒倒计时，按钮变为 `{n}s` 不可点击

### ⑥ 验证标准
- [ ] 正确 Token + 正确手机号：验证码写入数据库，5分钟后 SmsCodeExpire 超时
- [ ] 正确 Token + 错误手机号：返回错误，不更新验证码
- [ ] 错误 Token：返回报告不存在
- [ ] 前端倒计时60秒后可重新发送

---

## T11 后端接口：验证码校验 + 已读回写 `[S→T10]`

### ① 需求说明
PRD 3.6：客户输入验证码后，校验成功则标记已读，更新状态为"已查看"，并通知 LTO 检测完成。

### ② 接口定义

```
POST /api/DealerInspectReport/VerifyCode
[AllowAnonymous]
Content-Type: application/json

Request Body:
{
  "Token": "abc123...",
  "Phone": "15705181299",
  "Code": "123456"
}

Response（Code="0"）:
{ "Code": "0", "Message": "验证成功" }

Error:
{ "Code": "-1", "Message": "验证码错误" }
{ "Code": "-1", "Message": "验证码已过期，请重新获取" }
```

### ③ 数据模型
更新 `VOV_DealerVehicleInspectTask`：
- `IsViewed = 1`
- `ViewedTime = DateTime.Now`
- `ReportStatus = 3`
- `SmsCode = null`（防止重复使用）
- `SmsCodeExpire = null`

### ④ 业务逻辑
```
1. 查询 WHERE ReportToken=Token，不存在 → Error
2. 校验 Phone == task.CustomerPhone
3. 校验 task.SmsCode == Code，不等 → Error("验证码错误")
4. 校验 DateTime.Now <= task.SmsCodeExpire，超时 → Error("验证码已过期")
5. UPDATE IsViewed=1, ViewedTime=Now, ReportStatus=3, SmsCode=null, SmsCodeExpire=null
6. 异步通知LTO（TryNotifyLto）：调用LTO回调接口（接口待LTO提供）；失败只记录日志不影响响应
7. 返回成功
```

### ⑤ 前端实现
文件：`src/pages/inspect-report/verify/index.tsx`  
设计图：`3.6-客户验证.png`

- 点击"确认"：调用此接口
- 成功后：`sessionStorage.setItem('report_verified_${token}', '1')`
- 根据 `window.innerWidth < 768` 跳转到 mobile 或 pc 报告页

### ⑥ 验证标准
- [ ] 正确验证码：数据库 IsViewed=1, ReportStatus=3, SmsCode=null
- [ ] 错误验证码：返回错误，SmsCode 不变
- [ ] 过期验证码（超5分钟）：返回过期错误
- [ ] 验证成功后再次调用 SendSmsCode，需重新发送（SmsCode已清空）
- [ ] 前端验证成功后跳转到报告页

---

## T12 后端接口：获取报告数据 `[S→T11]`

### ① 需求说明
PRD 3.6：客户验证通过后，读取完整的报告数据用于前端渲染。此接口同时供评估师预览和客户查看使用（通过 Token 区分）。

### ② 接口定义

```
GET /api/DealerInspectReport/GetReportData
[AllowAnonymous]
?token=abc123...

Response（Code="0"）:
{
  "Code": "0",
  "Data": {  // ReportDataVm
    "ID": 123,
    "InspectCode": "INSP20260526001",
    // 车辆信息
    "VehicleModelName": "2024款 沃尔沃XC60 B5",
    "Vin": "LVYP...",
    "PlateNumber": "浙G2R20F",
    "Mileage": "3.2",
    "FirstLicenseDate": "2024-07-05",
    // 经销商&检测师
    "DealerName": "杭州永达沃尔沃",
    "InspectUserName": "张三",
    "InspectTime": "2026-05-26T15:30:00",
    // 评估价格
    "IsPriceNegotiable": false,
    "EstimatedPrice": 180000.00,
    "TotalTransactionPrice": 195000.00,
    "ResidualValueAmount": 15000.00,
    "SubsidyAmount": 0,
    // 基本照片
    "ExteriorPhotos": "{...}",
    "InteriorPhotos": "{...}",
    "VinKeyPhotos": "{...}",
    "VehicleDocPhotos": "{...}",
    // 重点检测
    "IsBurned": false,
    "BurnedPhotos": "[]",
    "IsFlooded": false,
    "FloodedPhotos": "[]",
    "IsFrameAccident": false,
    "FrameAccidentPhotos": "[]",
    // 车辆检测
    "InspectData": "[...]",
    "PaintThicknessData": "[{\"name\":\"前盖\",\"value\":135},...]",
    // 漆面厚度标准值（前端据此渲染超标红色）
    "PaintThicknessStandards": [
      {"Name":"前盖","Min":120,"Max":160},
      {"Name":"左前翼子板","Min":110,"Max":150},
      {"Name":"左A柱外板","Min":130,"Max":150},
      {"Name":"左前门","Min":110,"Max":160},
      {"Name":"左上边梁外板","Min":110,"Max":140},
      {"Name":"左后门","Min":100,"Max":160},
      {"Name":"左C柱外板","Min":70,"Max":100},
      {"Name":"左后翼子板（外板）","Min":130,"Max":160},
      {"Name":"车顶","Min":110,"Max":140},
      {"Name":"后盖","Min":100,"Max":140},
      {"Name":"右后翼子板（外板）","Min":120,"Max":150},
      {"Name":"右C柱外板","Min":70,"Max":90},
      {"Name":"右后门","Min":120,"Max":160},
      {"Name":"右上边梁外板","Min":120,"Max":150},
      {"Name":"右前门","Min":110,"Max":150},
      {"Name":"右A柱外板","Min":120,"Max":150},
      {"Name":"右前翼子板","Min":110,"Max":150}
    ]
  }
}
```

### ③ 数据模型
查询 `VOV_DealerVehicleInspectTask WHERE ReportToken=token AND IsViewed=1`，同时关联查询经销商名称（FROM VOV_Dealer WHERE Code=DealerCode）。

### ④ 业务逻辑
```
1. 查询 WHERE ReportToken=token，不存在 → Error("报告不存在")
2. 校验 IsViewed = 1，否则 → Error("请先完成手机验证")
3. 查询经销商名称：DealerName
4. 构建 ReportDataVm，特别处理：
   - PaintThicknessStandards：硬编码17项标准值
   - DealerName：从 VOV_Dealer/VOV_DealerAccount 表获取
5. 返回 ReportDataVm
```

### ⑤ 前端实现
文件：`src/pages/inspect-report/mobile/index.tsx`、`src/pages/inspect-report/pc/index.tsx`  
设计稿：`d:\Projects\ProjectV\企微检测\检测报告\检测报告.html`（已导出的 HTML 参考文件）

- 接口路径：`/DealerInspectReport/GetReportData`（注意：不是旧的 `/InspectReport/GetReportData`）
- 所有字段对齐 `ReportDataVm` 结构

### ⑥ 验证标准
- [ ] IsViewed=false 时返回错误
- [ ] IsViewed=true 时返回完整报告数据
- [ ] PaintThicknessStandards 包含17条数据
- [ ] DealerName 有正确的经销商名称

---

## T13 后端接口：PC端列表 + 导出 `[P]`

### ① 需求说明
PRD 3.7：厂端管理员查看全经销商的检测任务，支持筛选和导出。

### ② 接口定义

```
GET /api/VehicleInspect/GetInspectTaskListPC
[Authenticate]（需厂端权限）

Query Parameters:
  Vin, PlateNumber, Status(int?), CustomerName
  StartDate, EndDate, Page（JSON {"Index":1,"Size":20}）

Response:
{
  "Data": [
    {
      "ID": 123,
      "InspectCode": "INSP...",
      "Vin": "LVY...",
      "PlateNumber": "浙G2R20F",
      "CarSeries": "XC60",
      "CustomerName": "张智勇",
      "DealerCode": "CN001",
      "ReportStatus": 3,
      "InspectUserName": "张三",
      "CreateTime": "2026-05-26T10:30:00",
      "InspectTime": "2026-05-26T15:30:00",
      "ViewedTime": "2026-05-26T16:00:00",
      "ReportToken": "abc..."   // 仅 ReportStatus=3 时返回，其余为null
    }
  ],
  "DataTotal": 200
}

POST /api/VehicleInspect/ExportInspectTasks
[Authenticate]
请求体同查询条件（不含Page），返回 Excel 文件流。
导出字段：编号/VIN/车牌号/品牌车型/客户名称/经销商代码/检测状态/评估师/创建时间/检测时间/查看时间
```

### ③ 数据模型
查询 `VOV_DealerVehicleInspectTask`，不按 DealerCode 过滤（全量）。

### ④ 业务逻辑（GetInspectTaskListPC）
```
1. 无DealerCode过滤（厂端查全量）
2. 同 T03 的查询条件逻辑
3. ReportToken：ReportStatus != 3 时返回 null
```

**业务逻辑（ExportInspectTasks）**：
```
1. 不分页，查全量数据
2. 使用 NPOI 生成 Excel，列顺序：编号/VIN/车牌号/品牌车型/客户名称/经销商代码/检测状态/评估师/创建时间/检测时间/查看时间
3. 检测状态枚举：0=进行中, 1/2=待查看, 3=已查看, -1=已作废
4. 返回 application/vnd.openxmlformats-officedocument.spreadsheetml.sheet 文件流
```

### ⑤ 前端实现（PC管理端 project-v-admin）
文件：`project-v-admin/src/views/usedcar/inspect/InspectTaskList.vue`（新建）  
设计图：`3.7-PC列表.png`

- 菜单：二手车 / 检测管理 / 经销商收车检测（需在菜单配置中新增）
- 操作列："查看检测报告"仅 ReportStatus=3 时显示，点击新窗口打开 `{H5BaseUrl}/inspect-report/{ReportToken}`
- "导出"按钮：调用 ExportInspectTasks 下载 Excel

### ⑥ 验证标准
- [ ] 厂端登录后能查到所有经销商的数据（不受 DealerCode 限制）
- [ ] ReportStatus!=3 的任务操作列无"查看报告"按钮
- [ ] 导出 Excel 包含正确列名和数据

---

---

# 阶段 2：前端 H5 页面实现

---

## T14 前端：检测任务列表页 `[P]`

### ① 需求说明
PRD 3.2：企微工作台 → 二手车 → 检测管理（新增菜单）

### ② 接口定义
调用 `GET /api/VehicleInspect/GetInspectTaskList`（见 T03）

### ③ 数据模型（前端状态）
```typescript
// 筛选状态
vinKeyword: string
selectedStatus: 0 | 1 | 3 | undefined  // undefined=全部
// 列表数据
items: InspectTaskListItem[]
total: number
page: number
```

### ④ 业务逻辑
1. 进入页面自动加载第一页（不带筛选条件）
2. 搜索/筛选改变后重新从第一页加载
3. 下拉刷新 / 上拉加载更多（ListPage 组件已实现）
4. 点击卡片 → `router.push({ name: 'InspectTaskStep1', query: { inspectId: item.ID } })`
5. 点击"新建"按钮 → `router.push({ name: 'InspectTaskStep1' })` （无 inspectId）

### ⑤ 前端实现
文件：`src/pages/inspect-task-list/index.tsx`  
设计图：`3.2-列表-3.png`（卡片样式）

**卡片结构**：
```
┌────────────────────────────┐
│ INSP20260526001   [进行中] │  ← 进行中蓝/待查看橙/已查看绿
│ 旧车VIN LVYPDM1D1SP133126 │
│ 创建时间 2026-05-26 10:30  │
└────────────────────────────┘
```

**筛选区**（顶部固定）：
- 搜索框：`placeholder="请输入旧车VIN进行查询"`
- Chip 行：旧车车系 ∧ | 单据创建时间 ∧ | 状态 ∧（激活时蓝色背景）

**新建按钮**：底部固定，蓝色，文字"新建"

### ⑥ 验证标准
- [ ] 列表加载正确，分页正常
- [ ] 状态筛选：选择"待查看"→ ReportStatus 1和2 的任务均显示
- [ ] VIN 搜索模糊匹配
- [ ] 状态标签颜色：进行中=蓝色，待查看=橙色，已查看=绿色
- [ ] 点击卡片进入 Step1
- [ ] 点击新建进入 Step1（无inspectId）

---

## T15 前端：Step1 基本信息页 `[P]`

### ① 需求说明
PRD 3.3.1：行驶证OCR + 车辆基本信息 + 检测人 + 联系人

### ② 接口定义
- `GET /api/VehicleInspect/GetInspectTaskDetail`（回显）
- `POST /api/VehicleInspect/SaveInspectTask`（保存）
- `POST /api/VehicleInspect/RecognizeDrivingLicense`（OCR识别）

### ③ 数据模型（前端状态）
```typescript
inspectId: number | undefined  // undefined=新建
source: 'LTO' | 'MANUAL'      // 控制VIN是否只读
// 行驶证
drivingLicenseFiles: UploaderFileListItem[]
// 车辆信息（均可编辑，除LTO任务的VIN）
vehicleModelId, carSeries, vin(只读if LTO), plateNumber, bodyColor, mileage
owner, ownerType, useType, factoryDate, firstLicenseDate
// 检测人 & 联系人
inspectUserName, customerName, customerPhone
```

### ④ 业务逻辑
```
进入页面：
1. inspectId 有值 → getInspectTaskDetail 回显数据
2. inspectId 无值 → 表单空白，Source='MANUAL'

点击"保存"：
3. 调用 saveInspectTask，传入当前填写的字段（保存不跳转）

点击"下一步"：
4. 必填校验（所有标*字段不为空）
5. 通过 → saveInspectTask → 成功后跳转 Step2（携带 inspectId）

上传行驶证照片：
6. BasicUploader 上传后获取 OSS URL
7. 调用 RecognizeDrivingLicense { ImageUrl: url }
8. 返回数据 → 逐字段回填（仅回填为空的字段，不覆盖用户已填的）
9. OCR失败 → Toast "识别失败，请手动填写"
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-1-basic-info/index.tsx`  
设计图：`3.3.1-基本信息.png`

**页面布局（白卡行列表单风格）**：
```
┌ 行驶证信息 ─────────────────┐
│ [行驶证图片上传区]           │
└─────────────────────────────┘
┌ 车辆信息 ───────────────────┐
│ *品牌车型  [2023款沃尔沃XC60 >] │
│ *车架号    [LVYPDM1D1SP133126]  │ ← LTO任务只读灰色
│ *车牌号码  [请输入]             │
│ *车身颜色  [请输入]             │
│ *表显里程  [请输入 万km]        │
│  出厂日期  [YYYY-MM >]          │
│ *首次上牌日期 [YYYY-MM-DD >]   │
│ *所有人    [请输入]             │
│ *所有人性质 [请选择 >]          │
│ *使用性质  [请选择 >]           │
│ *检测人    [请输入]             │
└─────────────────────────────┘
┌ 身份信息 ───────────────────┐
│ *姓名      [请输入]             │
│ *联系方式  [请输入]             │
└─────────────────────────────┘
[ 保存 ]  [ 下一步 (蓝) ]
```

**必填字段校验**：
- 车架号（仅手动创建）、车牌号码、车身颜色、表显里程、首次上牌日期、所有人、所有人性质、使用性质、检测人、姓名、联系方式
- 未填写字段标红 + Toast 提示

### ⑥ 验证标准
- [ ] LTO 任务进入：VIN 只读显示，其余字段可编辑
- [ ] 手动新建：VIN 可编辑，必填校验
- [ ] 上传行驶证 → OCR 自动回填车牌/所有人等字段
- [ ] 必填校验失败时Toast提示具体字段
- [ ] 保存后重新进入，数据正确回显

---

## T16 前端：Step2 基本照片 & 重点检测页 `[P]`

### ① 需求说明
PRD 3.3.2：上传基本照片（外观5张+内饰4张+车架号1张+手续可选）+ 重点检测（火烧/水淹/结构损伤，各最多3张）

### ② 接口定义
- `GET /api/VehicleInspect/GetInspectTaskDetail`（回显）
- `POST /api/VehicleInspect/SaveInspectTask`（保存）
- OSS 上传接口（复用现有）

### ③ 数据模型（前端状态）

照片数据结构（均为 JSON 对象/数组字符串存储）：
```typescript
// 各为 { [label]: UploaderFileListItem | undefined } 结构
vinPhoto: UploaderFileListItem | undefined          // 车架号，必填1张
docPhotos: { 登记证?, 交强险保单? }                // 可选
exteriorPhotos: { 车辆正前,发动机,车辆左侧,车辆后侧,后备箱 }  // 各必填1张
interiorPhotos: { 主驾驶座椅,仪表盘,后排左,仪表台 }         // 各必填1张

hasVehicleDoc: boolean  // 车辆手续有/无
isBurned: boolean; burnedPhotos: UploaderFileListItem[]     // 最多3张
isFlooded: boolean; floodedPhotos: UploaderFileListItem[]
isFrameAccident: boolean; frameAccidentPhotos: UploaderFileListItem[]
```

### ④ 业务逻辑
```
进入页面：
1. getInspectTaskDetail 回显，解析各照片JSON，反填到对应 ref

点击"下一步"：
2. 必填照片校验（车架号/外观5张/内饰4张）
3. 构建 JSON payload：
   ExteriorPhotos = JSON.stringify({"车辆正前":"url",...})
   BurnedPhotos = JSON.stringify(["url1",...])（最多3张）
   ...
4. 调用 saveInspectTask，保存成功后跳转 Step3

点击"上一步"：直接跳转 Step1（不保存）
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-2-basic-photos/index.tsx`  
设计图：`3.3.2-基本照片.png`（完整布局）、`3.3.2-重点检测.png`（重点检测展开）

**页面布局**：
```
┌ 车架号(前挡风玻璃) * ─────────┐
│ [+] ⚠车架号 *               │  ← 1格上传，必填1张，黄色❗
└────────────────────────────────┘
┌ 车辆手续(全部可选) 〇无 〇有 ──┐
│ (选"有"展开) [+]登记证 [+]交强险保单 │
└────────────────────────────────┘
┌ 外观 * ────────────────────────┐
│ [+]车辆正前* [+]发动机* [+]车辆左侧* │
│ [+]车辆后侧*  [+]后备箱*            │
└────────────────────────────────┘
┌ 内饰 * ────────────────────────┐
│ [+]主驾驶座椅* [+]仪表盘* [+]后排左* │
│ [+]仪表台*                          │
└────────────────────────────────┘
┌ 重点检测 * ────────────────────┐
│ 火烧*       〇无 🔵有            │
│ (有时)：[+][+][+] ⚠火烧(最多3张) │
│ 水淹*       🔵无 〇有            │
│ 结构损伤*   🔵无 〇有            │
└────────────────────────────────┘
[ 上一步 ]  [ 下一步 (蓝) ]
```

**上传组件规格**：
- 每个格子宽度：`(屏幕宽-32-16)/3` px（3列网格）
- 黄色感叹号图标：`⚠` 颜色 `#FFAD14`，显示在格子标签左侧
- 选择"有"时：有照片则显示已上传缩略图，点击可删除重传

### ⑥ 验证标准
- [ ] 不上传车架号照片直接点下一步 → Toast "请上传车架号照片"
- [ ] 外观/内饰5/4项必填校验正确
- [ ] 选"有"（火烧）后上传3张 → 保存成功；上传第4张 → 报错（后端校验）
- [ ] 保存后重进，所有照片正确回显

---

## T17 前端：Step3 车辆检测 & 漆面厚度页 `[S→T01,T07]`

### ① 需求说明
PRD 3.3.3：骨架/外观/内饰三类检测（逐项打点选项+照片）+ 漆面厚度17项录入

### ② 接口定义
- `GET /api/VehicleInspect/GetInspectTaskDetail`（获取车牌/VIN显示 + PaintThicknessData回显）
- `GET /api/VehicleInspect/GetInspectCategories`（获取检测树 + InspectData回显）
- `POST /api/VehicleInspect/SaveInspectTask`（保存 InspectData + PaintThicknessData）

### ③ 数据模型（前端状态）
```typescript
// 来自 GetInspectCategories
inspectCategories: InspectCategories[]   // 骨架/外观/内饰三大类

// Tab 索引（0=骨架,1=外观,2=内饰,3=漆面厚度）
activeTab: 0 | 1 | 2 | 3

// 漆面厚度数据（17项，值为用户输入的μm字符串）
paintValues: { [name: string]: string }  
// 例: { "前盖": "135", "左前翼子板": "128", ... }

// Sidebar 激活项（当前选中的检测类别索引）
activeCategory: number
```

**InspectData JSON 格式**（保存时序列化）：
```json
[
  {
    "CategoryId": 1,
    "InspectItemId": 5,
    "Id": 12,
    "IsCheck": true,
    "Images": ["https://oss.../img1.jpg"],
    "InputValue": ""
  }
]
```

**PaintThicknessData JSON 格式**（保存时序列化）：
```json
[
  {"name": "前盖", "value": 135},
  {"name": "左前翼子板", "value": 128}
]
```

### ④ 业务逻辑
```
进入页面：
1. 并发调用 getInspectTaskDetail（获取车型卡片信息）和 getInspectCategories（获取检测树）
2. 恢复漆面厚度数据：解析 PaintThicknessData JSON 回填到 paintValues

车辆检测（Tab 0/1/2）：
3. 左侧 Sidebar 显示分类（骨架/外观/内饰），每项显示 "已检查数/总数"
4. 右侧列表显示当前分类的检测部位
5. 点击部位 → 进入 VehicleDetectionFormPage（选项选择+照片上传）
6. 回退后检测数据更新到 inspectCategories（通过 vehicleDetectionStore 同步）

漆面厚度 Tab：
7. 显示17个输入格，用户输入数值
8. 实时校验：value < min 或 value > max → 输入框红色边框+红色文字

点击"保存"：
9. 序列化 getAllInspectOptions(inspectCategories) → InspectData JSON
10. 过滤非空的 paintValues → PaintThicknessData JSON
11. 调用 saveInspectTask({ InspectData, PaintThicknessData })

点击"下一步"：12. 先保存 → 成功后跳转 Step4
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-3-key-inspect/index.tsx`  
设计图：`3.3.3-车辆检测-1.png`（骨架Tab+左右布局）、`3.3.3-车辆检测-2.png`（漆面厚度Tab）、`3.3.3-漆面厚度.png`（漆面厚度输入框样式）

**漆面厚度 17项标准值**：
```
前盖:120~160 / 左前翼子板:110~150 / 左A柱外板:130~150 / 左前门:110~160
左上边梁外板:110~140 / 左后门:100~160 / 左C柱外板:70~100 / 左后翼子板(外板):130~160
车顶:110~140 / 后盖:100~140 / 右后翼子板(外板):120~150 / 右C柱外板:70~90
右后门:120~160 / 右上边梁外板:120~150 / 右前门:110~150 / 右A柱外板:120~150
右前翼子板:110~150
```

### ⑥ 验证标准
- [ ] 骨架Tab有40个检测项，点击检测项进入选项页
- [ ] 完成检测的部位在左侧列表显示绿色 ✓
- [ ] 漆面厚度：输入127（在120-160范围内）→ 正常；输入200 → 红色
- [ ] 保存后重进，检测数据和漆面厚度数据正确回显

---

## T18 前端：Step4 检测详情（评估价格）页 `[P]`

### ① 需求说明
PRD 3.4：检测结果汇总 + 评估价格录入 + 报告生成

### ② 接口定义
- `GET /api/VehicleInspect/GetInspectTaskDetail`（回显数据 + 获取 ReportStatus）
- `POST /api/VehicleInspect/SaveInspectTask`（保存价格数据）
- `GET /api/VehicleInspect/PreviewReport`（预览报告）
- `POST /api/VehicleInspect/GenerateReport`（生成报告）

### ③ 数据模型（前端状态）
```typescript
detail: InspectTaskDetailVm | null      // 完整任务数据（含ReportStatus）
isPriceNegotiable: boolean              // 价格面议开关
estimatedPrice: string                  // 车辆评估价格（面议时不可编辑）
residualValueAmount: string             // 残值保障金金额
subsidyAmount: string                   // 国补/区补补贴
totalTransactionPrice: string           // 本次交易总价（面议时不可编辑）
```

### ④ 业务逻辑
```
进入页面：
1. getInspectTaskDetail 获取数据，回显评估价格字段和 ReportStatus

价格面议开关：
2. 开启 → estimatedPrice/totalTransactionPrice 显示"面议"，不可编辑
3. 关闭 → 两者变为必填输入框

点击"检测报告预览"（任何状态均可点）：
4. 调用 saveInspectTask（保存当前价格）
5. 调用 previewReport → 渲染报告预览（新路由或底部弹层）

点击"生成检测报告"（仅 ReportStatus=0 时显示）：
6. 弹出 Dialog：标题"确认生成"，内容"您的姓名（{InspectUserName}）将作为检测师签名展示在报告中，确认生成？"
7. 确认 → saveInspectTask（保存价格）→ generateReport({ID})
8. 成功 → Dialog 显示"检测报告已生成"+ 报告URL + "复制链接"按钮
9. 页面刷新 ReportStatus 变为 2，按钮变为仅"检测报告预览"

ReportStatus ≥ 1 时：
10. 所有价格字段只读（不显示输入框，显示静态文本）
11. 底部按钮仅"检测报告预览"（全宽蓝色）
```

### ⑤ 前端实现
文件：`src/pages/inspect-task-detail/step-4-vehicle-inspect/index.tsx`  
设计图：`3.4-评估价格-进行中.png`、`3.4-评估价格-面议.png`、`3.4-评估价格-待查看.png`、`3.4-评估价格-已查看.png`

**页面布局**：
```
┌ 车型信息卡片 ────────────────┐
│ 奥迪A6L（车型名）   [进行中] │
│ 2006款 奥迪A6L 3.0 自动尊贵型│
│ 车牌 皖RG8786  VIN LDC...    │
└────────────────────────────┘
  *基本信息录入          已完成 >
  *基本照片信息录入      已完成 >
  *检测信息录入          已完成 >
┌ 交易评估 ─────────────────── 价格面议 ○ ┐
│ *车辆评估价格    [请输入]                │
│  残值保障金金额  [请输入]                │
│  国补/区补补贴   [请输入]                │
│ *本次交易总价金额 [请输入]               │
└─────────────────────────────────────────┘
[ 检测报告预览(灰) ]  [ 生成检测报告(蓝) ]
```

### ⑥ 验证标准
- [ ] 面议开关打开：车辆评估价格/总价显示"面议"不可编辑
- [ ] ReportStatus=0：显示"预览"+"生成"两个按钮
- [ ] ReportStatus=1/2/3：只显示"预览"按钮（全宽）
- [ ] 生成确认弹框：检测师姓名正确显示
- [ ] 生成成功后：状态变为"待查看"，按钮变化

---

## T19 前端：客户验证页 `[P]`

### ① 需求说明
PRD 3.6：客户打开报告链接，首先进入验证页输入手机号和验证码

### ② 接口定义
- `POST /api/DealerInspectReport/SendSmsCode`（发送验证码）
- `POST /api/DealerInspectReport/VerifyCode`（验证码校验）

### ③ 数据模型（前端状态）
```typescript
token: string       // 从路由参数获取
phone: string       // 用户输入的手机号（须与任务CustomerPhone一致）
code: string        // 6位验证码
countdown: number   // 倒计时秒数（0=可发送）
```

### ④ 业务逻辑
```
进入路由 /inspect-report/:token/verify：
1. 从 sessionStorage 检查是否已验证（report_verified_{token}）
   若已验证 → 直接跳转 mobile/pc 报告页

点击"发送验证码"：
2. 前端校验：手机号11位格式
3. 调用 sendSmsCode({Token, Phone})
4. 成功 → 倒计时60秒，按钮变灰不可点

点击"确认"：
5. 调用 verifyCode({Token, Phone, Code})
6. 成功：
   sessionStorage.setItem('report_verified_{token}', '1')
   window.innerWidth < 768 → /inspect-report/{token}/mobile
   else → /inspect-report/{token}/pc
7. 失败 → Toast 显示错误消息
```

### ⑤ 前端实现
文件：`src/pages/inspect-report/verify/index.tsx`  
设计图：`3.6-客户验证.png`

**页面布局（深色背景 + 白卡弹窗）**：
```
背景：深蓝渐变 #1a1a2e → #0f3460
┌ 验证登录 ─────────────────── × ┐
│ 手机号码                         │
│ [📱 请输入手机号码]               │
│ 验证码                           │
│ [🔒 请输入] [发送验证码 / 60s]  │
│ ℹ 验证码将通过短信发送...         │
│ [ 确认 →          ]              │  ← 深蓝渐变按钮
└─────────────────────────────────┘
```

### ⑥ 验证标准
- [ ] 手机号格式错误 → Toast "请输入正确的手机号"
- [ ] 正确手机号 → 发送成功，60秒倒计时
- [ ] 验证码错误 → Toast "验证码错误"
- [ ] 验证成功 → 手机端跳转 mobile，PC端跳转 pc
- [ ] 已验证的 Token 再次打开链接 → 直接跳报告页（不再验证）

---

## T20 前端：检测报告手机端页面 `[S→T12]`

### ① 需求说明
PRD 3.4.2 检测报告取值逻辑：客户手机查看完整检测报告

### ② 接口定义
- `GET /api/DealerInspectReport/GetReportData?token=xxx`

### ③ 数据模型（前端）
```typescript
reportData: ReportDataVm  // 见T12接口定义
// 解析字段
exteriorList: { label: string; url: string }[]  // 外观照片列表
interiorList: { label: string; url: string }[]  // 内饰照片列表
paintData: { name: string; value: number; min: number; max: number; isOutRange: boolean }[]
abnormalItems: { item: string; option: string; images: string[] }[]  // 异常项目列表
```

### ④ 业务逻辑
```
1. 调用 GetReportData，获取 ReportDataVm
2. 解析 ExteriorPhotos JSON → exteriorList（用于轮播展示）
3. 解析 InspectData JSON → 过滤 IsCheck=true 的选项 → 构建 abnormalItems
   格式："车顶丨划痕"（用｜连接检测项名和异常项名）
4. 合并 PaintThicknessData 和 PaintThicknessStandards → 判断每项是否超标
5. 超标项（value < min 或 value > max）→ 字体红色
```

### ⑤ 前端实现
文件：`src/pages/inspect-report/mobile/index.tsx`  
设计图：`3.4.2-生成报告.png`（右侧报告样式）

**报告页面结构**（滚动页）：
```
标题：二手车检测报告
品牌车系车型：2024款 沃尔沃XC60 B5

┌ 评估价格 ───────────────────────┐
│ 本次交易总价金额  面议/195000元  │
│ 车辆评估价格      面议/180000元  │
│ 残值保障金金额    15000元        │
│ 国补/区补等补贴   0              │
└─────────────────────────────────┘

┌ 车辆信息 ───────────────────────┐
│ 车架号  VIN                      │
│ 车牌号  浙G2R20F                 │
│ 表显里程 3.2万km                 │
│ 首次上牌日期 2024-07-05          │
└─────────────────────────────────┘

基本照片（各 Swiper 左右滑动）
  外观 [照片1] [照片2] ...
  内饰 [照片1] ...
  车架号 [照片]
  手续 [照片] ...

┌ 重点检测 ───────────────────────┐
│ ❗火烧（红色，可点击看照片）      │  ← 有火烧
│ ✓ 无水淹（蓝色，不可点击）      │
│ ✓ 无结构损伤（蓝色）            │
└─────────────────────────────────┘

┌ 车辆检测 ───────────────────────┐
│ 异常照片 [Swiper左右查看]        │
│ 异常项目：                       │
│   车顶丨划痕                     │
│   左前门丨喷漆                   │
└─────────────────────────────────┘

漆面厚度：
  前盖         135 μm   (正常)
  左前翼子板   190 μm   ← 红色超标
  ...

底部：经销商名称
      [签名字体] 张三
```

### ⑥ 验证标准
- [ ] 评估价格：IsPriceNegotiable=true 时显示"面议"，false 时显示具体金额
- [ ] 基本照片可左右滑动
- [ ] 重点检测：有问题显示红色❗，无问题显示蓝色✓
- [ ] 异常项目格式：`名称丨异常`（使用中文竖线｜）
- [ ] 漆面厚度超标项文字红色
- [ ] 检测师签名显示签名字体（用 font-family 模拟或 CSS 手写字体）

---

## T21 前端：检测报告 PC 端页面 `[S→T12]`

### ① 需求说明
与 T20 相同内容，宽屏多列布局适配

### ② 接口定义
同 T20

### ③ 数据模型
同 T20

### ④ 业务逻辑
同 T20，布局为宽屏多列

### ⑤ 前端实现
文件：`src/pages/inspect-report/pc/index.tsx`

- 对齐 `ReportDataVm` 字段（去掉旧的 `VehicleInfo` 结构）
- 宽屏：评估价格/车辆信息双列，照片网格展示，漆面厚度表格更宽

### ⑥ 验证标准
- [ ] PC端（宽度≥768px）打开报告链接，跳转此页面
- [ ] 所有字段数据与手机端相同
- [ ] 宽屏布局不溢出

---

---

# 阶段 3：外部系统集成（并行于阶段 4）

---

## T22 企微发送集成 `[S→T09]`

### ① 需求说明
PRD 3.5.1：VIN已创建官方保客群且评估师已加群时，通过企微群SOP任务把报告推送给评估师。

### ② 接口定义

**调用企微查群接口**（根据VIN+经销商）：
```
接口文档：https://confluence.project-v.internal/.../API文档#接口1-根据vin码和经销商查询群接口
负责人：张伟（BA）
```

**调用群SOP任务个性化消息接口**：
```
POST /base/api/wechatSopTask/sendSopTaskMessage
服务：dse-wechat-base-ability（企微基础能力服务）

Header:
  Appkey:    {Appkey}
  Signature: {Signature}
  Timestamp: {Timestamp}
  Nonce:     {Nonce}

Body:
{
  "taskId":                 117,           // 主任务ID（检测报告推送模板ID，待张伟确认）
  "ownerUserId":            "123456",      // 执行任务顾问的认证中心 UserId（= InspectUserId）
  "targetId":               "wrYcvgVA...", // 目标群ID（由查群接口返回的 GroupId）
  "type":                   0,             // 0=群（默认），1=外部联系人
  "customizeParamValueMap": {
    "reportUrl": "{ReportUrl}"             // 占位符名称待张伟与企微侧确认
  },
  "repeatSendStatus":       0              // 0=不重复发送
}

Response:
{
  "code": 0,    // 0=成功；9001=任务不存在/已禁用；9002=任务已执行；9003=顾问不在群中；9999=未知异常
  "msg":  "..."
}

负责人：张伟（BA）
待确认：taskId（模板ID）和 customizeParamValueMap 中的占位符名称
```

### ③ 数据模型
无新增数据模型（复用任务表 ReportStatus 字段）

### ④ 业务逻辑
```
// 替换 TrySendViaWecom 中的 TODO 占位
1. 调用查群接口（Vin, DealerCode）→ 返回 { GroupId, EvaluatorJoined }
2. IF GroupId 有值 AND EvaluatorJoined=true:
   调用 sendSopTaskMessage({
     taskId: <配置值>,
     ownerUserId: task.InspectUserId,
     targetId: GroupId,
     type: 0,
     customizeParamValueMap: { "reportUrl": reportUrl }
   })
   code=0 → return true
   code=9003（顾问不在群）→ return false（降级短信）
   其他非0 → LogHelper.WriteError → return false（降级短信）
3. ELSE → return false（降级短信）
4. 任何异常 → LogHelper.WriteError(ex) → return false
```

### ⑤ 前端实现
无（纯后端逻辑）

### ⑥ 验证标准
- [ ] VIN有保客群+评估师已加群：评估师企微工作台收到任务推送
- [ ] VIN无保客群：降级短信，不报错
- [ ] 企微接口返回9003（顾问不在群）：降级短信，不报错
- [ ] 企微接口异常：降级短信，日志记录

---

## T23 短信发送集成 `[S→T09, 待模板确认]`

### ① 需求说明
PRD 3.5.2 + 3.6 验证码短信：两个场景需要发短信

### ② 接口定义
短信内容模板（待业务方确认）：
- **报告通知短信**：`{客户姓名}您好，您的车辆检测报告已生成，点击链接查看：{ReportUrl}`
- **验证码短信**：`您的检测报告验证码为：{Code}，5分钟内有效，请勿泄露。`

### ③ 数据模型
无新增

### ④ 业务逻辑
```
// 替换 TrySendViaSms 和 T10 中的 TODO 占位
1. 复用现有短信服务（查找 ProjectVUCM.Common 中的 SmsHelper 或相关类）
2. 报告通知：发送到 task.CustomerPhone，内容含 reportUrl
3. 验证码：发送到入参 Phone，内容含6位验证码
```

### ⑤ 前端实现
无

### ⑥ 验证标准
- [ ] 发送报告通知：客户手机收到含报告链接的短信
- [ ] 发送验证码：客户手机收到6位验证码

---

## T24 LTO 完成回调集成 `[S→T11, 待接口确认]`

### ① 需求说明
PRD 3.6③：客户查看报告后，回写 LTO 检测已完成

### ② 接口定义
LTO 回调接口（待 LTO 侧提供，预估格式）：
```
POST {LtoCallbackUrl}/inspection/complete
Header: Authorization: Bearer {LtoToken}
Body: { "LtoTaskId": "xxx", "InspectCode": "INSP...", "CompletedAt": "2026-05-26T16:00:00" }
```

### ③ 数据模型
无新增

### ④ 业务逻辑
```
// 替换 TryNotifyLto 中的 TODO 占位
1. 构建请求体：{ LtoTaskId=task.LtoTaskId, InspectCode=task.InspectCode, CompletedAt=Now }
2. 若 LtoTaskId 为空（手动创建任务）→ 跳过，不调用
3. 调用 LTO 接口（捕获所有异常，失败只记录日志）
```

### ⑤ 前端实现
无

### ⑥ 验证标准
- [ ] 客户验证成功后 LTO 系统收到完成通知
- [ ] 手动创建的任务（无LtoTaskId）不调用 LTO 接口
- [ ] LTO接口超时/报错：不影响客户查看报告，只记日志

---

---

# 阶段 4：PC 管理端（project-v-admin）

---

## T25 project-v-admin PC端检测任务列表 `[P]`

### ① 需求说明
PRD 3.7：厂端管理员在 PC 后台查看全经销商检测任务，支持筛选/导出/查看报告

### ② 接口定义
- `GET /api/VehicleInspect/GetInspectTaskListPC`
- `POST /api/VehicleInspect/ExportInspectTasks`

### ③ 数据模型（前端状态）
```typescript
// 查询条件
searchForm: {
  Vin: string, PlateNumber: string, Status: number | undefined,
  CustomerName: string, StartDate: string, EndDate: string
}
// 列表
list: PC端检测任务[]
total: number
page: { Index: number, Size: number }
```

### ④ 业务逻辑
```
1. 进入页面加载第一页数据
2. 点击"查询"：重新加载
3. 点击"清空"：重置 searchForm，重新加载
4. 点击"导出"：调用 ExportInspectTasks，触发文件下载
5. 操作列"查看检测报告"（仅 ReportStatus=3 显示）：
   新窗口打开 {H5BaseUrl}/inspect-report/{ReportToken}
```

### ⑤ 前端实现
文件：`project-v-admin/src/views/usedcar/inspect/InspectTaskList.vue`（新建）  
设计图：`3.7-PC列表.png`

**菜单配置**：
- 在 project-v-admin 菜单表中新增：二手车 → 检测管理 → 经销商收车检测

**列表字段**：
| 列名 | 字段 | 备注 |
|------|------|------|
| 编号 | InspectCode | |
| VIN | Vin | |
| 车牌号 | PlateNumber | |
| 品牌车型 | CarSeries | |
| 客户名称 | CustomerName | |
| 经销商代码 | DealerCode | |
| 检测状态 | ReportStatus | 0=进行中/1~2=待查看/3=已查看 |
| 评估师 | InspectUserName | |
| 创建时间 | CreateTime | |
| 检测时间 | InspectTime | |
| 查看时间 | ViewedTime | |
| 操作 | — | 已查看时显示"查看检测报告" |

### ⑥ 验证标准
- [ ] 厂端登录能看到所有经销商数据
- [ ] 点击"查看检测报告"：新窗口打开报告页，不需要再次验证（已登录厂端账号）
  > 注：若业务方确认需要验证 → 需补充 T26 厂端免验证查看接口
- [ ] 导出：下载到 xlsx 文件，列名和数据正确
- [ ] 菜单权限正确，非厂端账号无法访问

---

---

# 阶段 5：联调 & 验收测试

---

## T26 评估师端全流程联调 `[S→T02~T18]`

### ① 需求说明
端到端验证完整评估师操作流程

### ② 联调步骤
```
1. 企微工作台 → 二手车 → 检测管理 → 列表页加载
2. 点击"新建" → Step1 填写基本信息 → 下一步
3. Step2 上传照片 → 下一步
4. Step3 选择检测项（骨架至少1项）+ 漆面厚度3项 → 下一步
5. Step4 填写评估价格 → 生成检测报告
6. 验证：企微收到任务推送（T22完成后）/ 或短信收到链接（T23完成后）
7. 报告状态变为"待查看"
```

### ③ 验收标准
- [ ] 整流程无JS报错
- [ ] 各步骤保存后重进数据回显正确
- [ ] 报告生成后状态更新正确
- [ ] 企微/短信推送成功

---

## T27 客户端全流程联调 `[S→T10~T21]`

### ① 需求说明
端到端验证客户查看报告流程

### ② 联调步骤
```
1. 客户收到链接 → 打开验证页
2. 输入联系人手机号 → 发送验证码 → 收到短信 → 输入验证码 → 确认
3. 手机端（宽度<768）→ 跳转手机报告页
4. PC端（宽度≥768）→ 跳转PC报告页
5. 报告数据完整展示，漆面厚度超标项红色
6. 同一链接第二次打开 → 跳过验证直接看报告
7. 数据库：ReportStatus=3，IsViewed=1
```

### ③ 验收标准
- [ ] 验证码5分钟内有效
- [ ] 手机/PC端页面布局正确
- [ ] 重点检测颜色逻辑正确
- [ ] 异常项目格式 `名称丨异常` 正确

---

## 待确认事项

| # | 事项 | 阻塞任务 | 负责人 | 状态 |
|---|------|---------|-------|------|
| 1 | LTO下发接口认证方式（Token/IP白名单） | T02 | LTO侧 | ⏳ |
| 2 | 企微查群接口（根据VIN+经销商，已有文档） | T22 | 张伟（BA） | ✅ |
| 3 | 群SOP任务接口 taskId（模板ID）和占位符名称 | T22 | 张伟（BA） | ⏳ |
| 4 | LTO完成回调接口规范 | T24 | LTO侧 | ⏳ |
| 5 | 短信内容模板（报告通知 + 验证码） | T23 | 业务方 | ⏳ |
| 6 | 行驶证OCR服务选型 | T06 | 开发侧 | ⏳ |
| 7 | 厂端PC查看报告是否需要手机验证 | T25 | 业务方 | ⏳ |
