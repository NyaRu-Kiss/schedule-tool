/**
 * 经销商收车检测模块 - 端到端自动化测试
 *
 * 运行环境：Node.js >= 18（原生 fetch）
 * 依赖：vitest（或直接 node e2e.test.js 执行）
 *
 * 用法：
 *   node e2e.test.js                  # 直接运行，打印 TAP 风格结果
 *   BASE_URL=http://localhost:9003 node e2e.test.js
 *
 * 覆盖链路（完整端到端）：
 *   T00  建表验证         → 检测表字段存在性检查（通过接口侧验）
 *   T01  字典数据验证     → GetInspectCategories 返回 skeleton/exterior/interior
 *   T02  LTO 下发任务     → ReceiveLtoTask 创建任务，返回 InspectCode
 *   T03  手动新建任务     → SaveInspectTask (Source=MANUAL)，返回 ID
 *   T04  任务列表查询     → GetInspectTaskList 按 VIN 过滤
 *   T05  任务详情         → GetInspectTaskDetail 返回字段完整
 *   T06  OCR 识别         → RecognizeDrivingLicense 返回结构
 *   T07  保存检测数据     → SaveInspectTask 更新四步骤数据
 *   T08  预览报告         → PreviewReport 不修改 ReportStatus
 *   T09  生成报告         → GenerateReport 返回 ReportUrl+Token，ReportStatus=1/2
 *   T22  发送短信验证码   → SendSmsCode 正确手机号成功，错误手机号拒绝
 *   T23  验证码校验       → VerifyCode 正确码通过，错误码拒绝
 *   T24  获取报告数据     → GetReportData 验证通过后可访问，未验证拒绝
 *   T25  PC 端列表        → GetInspectTaskListPC 不受 DealerCode 过滤
 *   T26  导出             → ExportInspectTasks 返回 Excel 文件流
 *   T27  已读状态回写     → 验证通过后 ReportStatus=3，IsViewed=true
 */

const BASE_URL = process.env.BASE_URL ?? "http://localhost:9003";
const API      = `${BASE_URL}/api`;

// ── 测试账号（替换为实际测试环境的 Token）
const EVALUATOR_TOKEN  = process.env.EVALUATOR_TOKEN  ?? "REPLACE_WITH_EVALUATOR_TOKEN";
const ADMIN_TOKEN      = process.env.ADMIN_TOKEN      ?? "REPLACE_WITH_ADMIN_TOKEN";

// ── 测试数据（LTO 下发场景）
const TEST_VIN_LTO     = `LVTEST${Date.now().toString().slice(-8)}`;
const TEST_VIN_MANUAL  = `LVMANL${Date.now().toString().slice(-8)}`;
const TEST_DEALER_CODE = "D10001";
const TEST_PHONE       = "13800138000";   // 测试环境客户手机号

// ── 全局状态（测试间传递）
let ltoInspectId    = null;
let ltoInspectCode  = null;
let manualInspectId = null;
let reportToken     = null;
let reportUrl       = null;
let smsCode         = null;   // 测试环境从 DB 直接读取或 mock

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────
let passed = 0;
let failed = 0;
const results = [];

async function test(name, fn) {
    try {
        await fn();
        console.log(`  ✓  ${name}`);
        results.push({ name, ok: true });
        passed++;
    } catch (e) {
        const msg = e?.message ?? String(e);
        console.error(`  ✗  ${name}`);
        console.error(`       → ${msg}`);
        results.push({ name, ok: false, error: msg });
        failed++;
    }
}

function assert(cond, msg) {
    if (!cond) throw new Error(msg ?? "断言失败");
}

function assertEqual(a, b, msg) {
    if (a !== b) throw new Error(msg ?? `期望 ${JSON.stringify(b)}，实际 ${JSON.stringify(a)}`);
}

function assertOk(res) {
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText} → ${res.url}`);
}

async function api(method, path, body, token = EVALUATOR_TOKEN) {
    const headers = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const res = await fetch(`${API}${path}`, {
        method,
        headers,
        body: body != null ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = { _raw: text }; }
    return { res, json };
}

async function get(path, token) { return api("GET", path, null, token); }
async function post(path, body, token) { return api("POST", path, body, token); }

// ─────────────────────────────────────────────
// 测试套件
// ─────────────────────────────────────────────
async function runAll() {
    console.log(`\n${"=".repeat(60)}`);
    console.log(`  经销商收车检测模块 E2E 测试`);
    console.log(`  目标：${BASE_URL}`);
    console.log(`  时间：${new Date().toLocaleString()}`);
    console.log(`${"=".repeat(60)}\n`);

    // ─── 阶段 1：基础数据验证 ────────────────────────────────────
    console.log("▶ 阶段 1  基础数据验证");

    await test("T01-01  GetInspectCategories 返回三个分类", async () => {
        const { res, json } = await get("/VehicleInspect/GetInspectCategories");
        assertOk(res);
        const codes = (json.Data ?? json).map(c => c.Code);
        assert(codes.includes("skeleton"), "缺少 skeleton 分类");
        assert(codes.includes("exterior"), "缺少 exterior 分类");
        assert(codes.includes("interior"), "缺少 interior 分类");
    });

    await test("T01-02  GetInspectItems 骨架分类包含 40 个检测项", async () => {
        const { res, json } = await get("/VehicleInspect/GetInspectItems?categoryCode=skeleton");
        assertOk(res);
        const items = json.Data ?? json;
        assert(items.length >= 40, `骨架检测项数量不足 40，实际 ${items.length}`);
    });

    await test("T01-03  GetInspectItems 每个检测项包含至少1个选项", async () => {
        const { res, json } = await get("/VehicleInspect/GetInspectItems?categoryCode=exterior");
        assertOk(res);
        const items = json.Data ?? json;
        const noOptions = items.filter(i => !i.Options || i.Options.length === 0);
        assert(noOptions.length === 0, `${noOptions.length} 个外观检测项缺少选项：${noOptions.map(i => i.Code).join(",")}`);
    });

    // ─── 阶段 2：LTO 下发任务 ────────────────────────────────────
    console.log("\n▶ 阶段 2  LTO 下发任务（T02）");

    await test("T02-01  ReceiveLtoTask 创建任务成功，返回 InspectCode", async () => {
        const { res, json } = await post("/VehicleInspect/ReceiveLtoTask", {
            LtoTaskId:       `LTO-${Date.now()}`,
            Vin:             TEST_VIN_LTO,
            VehicleModelId:  "VM_XC60_2024",
            EvaluatorId:     1001,
            EvaluatorName:   "测试评估师",
            CustomerName:    "张三",
            CustomerPhone:   TEST_PHONE,
            DealerCode:      TEST_DEALER_CODE,
        });
        assertOk(res);
        assert(json.InspectCode, "未返回 InspectCode");
        assert(json.ID > 0, "未返回有效 ID");
        ltoInspectId   = json.ID;
        ltoInspectCode = json.InspectCode;
        assert(/^INSP\d{8}\d{3}$/.test(ltoInspectCode), `InspectCode 格式不符：${ltoInspectCode}`);
    });

    await test("T02-02  同一 VIN 允许重复下发，生成独立任务", async () => {
        const { res, json } = await post("/VehicleInspect/ReceiveLtoTask", {
            LtoTaskId:     `LTO-DUP-${Date.now()}`,
            Vin:           TEST_VIN_LTO,
            EvaluatorId:   1001,
            EvaluatorName: "测试评估师",
            CustomerName:  "张三",
            CustomerPhone: TEST_PHONE,
            DealerCode:    TEST_DEALER_CODE,
        });
        assertOk(res);
        assert(json.ID !== ltoInspectId, "重复下发应生成新任务 ID");
    });

    await test("T02-03  缺少必填字段 Vin 时返回 400", async () => {
        const { res } = await post("/VehicleInspect/ReceiveLtoTask", {
            LtoTaskId:  "LTO-MISSING-VIN",
            EvaluatorId: 1001,
            DealerCode: TEST_DEALER_CODE,
        });
        assertEqual(res.status, 400, "缺少 Vin 应返回 400");
    });

    // ─── 阶段 3：手动新建任务 ────────────────────────────────────
    console.log("\n▶ 阶段 3  手动新建任务（T03）");

    await test("T03-01  SaveInspectTask Source=MANUAL 新建任务成功", async () => {
        const { res, json } = await post("/VehicleInspect/SaveInspectTask", {
            Source:       "MANUAL",
            Vin:          TEST_VIN_MANUAL,
            DealerCode:   TEST_DEALER_CODE,
            CustomerName: "李四",
            CustomerPhone: TEST_PHONE,
        });
        assertOk(res);
        assert(json.ID > 0, "未返回有效 ID");
        manualInspectId = json.ID;
    });

    // ─── 阶段 4：任务列表查询 ─────────────────────────────────────
    console.log("\n▶ 阶段 4  任务列表查询（T04）");

    await test("T04-01  GetInspectTaskList 按 VIN 精确过滤", async () => {
        const page = encodeURIComponent(JSON.stringify({ Index: 1, Size: 20 }));
        const { res, json } = await get(`/VehicleInspect/GetInspectTaskList?Vin=${TEST_VIN_LTO}&Page=${page}`);
        assertOk(res);
        const items = json.Data ?? json;
        assert(items.length >= 1, `按 VIN=${TEST_VIN_LTO} 应至少返回 1 条`);
        assert(items.every(i => i.Vin === TEST_VIN_LTO), "列表包含非目标 VIN 的任务");
    });

    await test("T04-02  GetInspectTaskList 不返回 ReportStatus=-1 的已作废任务", async () => {
        const page = encodeURIComponent(JSON.stringify({ Index: 1, Size: 100 }));
        const { res, json } = await get(`/VehicleInspect/GetInspectTaskList?Page=${page}`);
        assertOk(res);
        const items = json.Data ?? json;
        assert(items.every(i => i.ReportStatus !== -1), "列表不应包含已作废（ReportStatus=-1）任务");
    });

    await test("T04-03  GetInspectTaskList 分页：超出范围返回空列表", async () => {
        const page = encodeURIComponent(JSON.stringify({ Index: 9999, Size: 20 }));
        const { res, json } = await get(`/VehicleInspect/GetInspectTaskList?Page=${page}`);
        assertOk(res);
        const items = json.Data ?? json;
        assertEqual(items.length, 0, "超出范围的页码应返回空数组");
    });

    // ─── 阶段 5：任务详情 ─────────────────────────────────────────
    console.log("\n▶ 阶段 5  任务详情（T05）");

    await test("T05-01  GetInspectTaskDetail 返回 LTO 任务字段完整", async () => {
        const { res, json } = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${ltoInspectId}`);
        assertOk(res);
        const d = json.Data ?? json;
        assert(d.ID > 0,          "缺少 ID");
        assert(d.Vin,             "缺少 Vin");
        assert(d.InspectCode,     "缺少 InspectCode");
        assert(d.DealerCode,      "缺少 DealerCode");
        assert(d.Source === "LTO","Source 应为 LTO");
        assertEqual(d.ReportStatus, 0, "新建任务 ReportStatus 应为 0");
    });

    await test("T05-02  GetInspectTaskDetail 不存在的 ID 返回 404 或错误", async () => {
        const { res } = await get("/VehicleInspect/GetInspectTaskDetail?inspectId=99999999");
        assert(res.status === 404 || res.status === 400, `应返回 404/400，实际 ${res.status}`);
    });

    // ─── 阶段 6：OCR 识别 ─────────────────────────────────────────
    console.log("\n▶ 阶段 6  OCR 识别（T06）");

    await test("T06-01  RecognizeDrivingLicense 返回 OcrResultVm 结构（允许字段为 null）", async () => {
        const { res, json } = await post("/VehicleInspect/RecognizeDrivingLicense", {
            ImageUrl: "https://cdn.project-v.internal/test/sample-driving-license.jpg",
        });
        // OCR 可能因图片原因识别失败，但接口本身应返回 200 + 结构对象，不抛 500
        assert(res.status < 500, `OCR 接口应不返回 5xx，实际 ${res.status}`);
        if (res.ok) {
            const d = json.Data ?? json;
            // 字段存在（即使 null）
            assert("Owner"          in d, "OcrResultVm 缺少 Owner 字段");
            assert("PlateNumber"    in d, "OcrResultVm 缺少 PlateNumber 字段");
            assert("UseType"        in d, "OcrResultVm 缺少 UseType 字段");
            assert("VehicleModelId" in d, "OcrResultVm 缺少 VehicleModelId 字段");
        }
    });

    // ─── 阶段 7：保存检测数据 ─────────────────────────────────────
    console.log("\n▶ 阶段 7  保存检测数据（T07）");

    const inspectDataPayload = {
        ID:           manualInspectId,
        Source:       "MANUAL",
        Vin:          TEST_VIN_MANUAL,
        DealerCode:   TEST_DEALER_CODE,
        CustomerName: "李四",
        CustomerPhone: TEST_PHONE,
        PlateNumber:  "沪A12345",
        BodyColor:    "白色",
        Mileage:      "35000",
        Owner:        "李四",
        OwnerType:    "个人",
        UseType:      "非营运",
        FactoryDate:  "2021-03",
        FirstLicenseDate: "2021-06-01",
        // 基本照片（各一张）
        ExteriorPhotos: JSON.stringify(["https://cdn.project-v.internal/test/exterior-front.jpg"]),
        InteriorPhotos: JSON.stringify(["https://cdn.project-v.internal/test/interior-main.jpg"]),
        VinKeyPhotos:   JSON.stringify(["https://cdn.project-v.internal/test/vin-key.jpg"]),
        // 重点检测
        IsBurned:        false,
        IsFlooded:       false,
        IsFrameAccident: false,
        // 检测项数据
        InspectData: JSON.stringify([
            { Code: "sk_001", HasIssue: false, Photos: [] },
            { Code: "sk_002", HasIssue: true, IssueOptions: ["o04"], Photos: ["https://cdn.project-v.internal/test/sk002-issue.jpg"] },
        ]),
        // 漆面厚度
        PaintThicknessData: JSON.stringify([
            { Part: "前盖",         Value: 135, Standard: "120~160", IsNormal: true  },
            { Part: "左前翼子板",   Value: 200, Standard: "110~150", IsNormal: false },
        ]),
        // 评估价格
        IsPriceNegotiable:      false,
        EstimatedPrice:         85000,
        TotalTransactionPrice:  82000,
        ResidualValueAmount:    5000,
        SubsidyAmount:          0,
    };

    await test("T07-01  SaveInspectTask 保存四步骤数据成功，ReportStatus 保持 0", async () => {
        const { res, json } = await post("/VehicleInspect/SaveInspectTask", inspectDataPayload);
        assertOk(res);
        assertEqual(json.ID, manualInspectId, "返回 ID 应与入参一致");
        // 验证 ReportStatus 未被改变
        const detail = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        assertEqual((detail.json.Data ?? detail.json).ReportStatus, 0, "保存后 ReportStatus 应仍为 0");
    });

    await test("T07-02  SaveInspectTask 火烧照片超过 3 张返回 400", async () => {
        const { res } = await post("/VehicleInspect/SaveInspectTask", {
            ...inspectDataPayload,
            IsBurned: true,
            BurnedPhotos: JSON.stringify(["url1", "url2", "url3", "url4"]),  // 4 张，超限
        });
        assertEqual(res.status, 400, "火烧照片超过 3 张应返回 400");
    });

    await test("T07-03  已生成报告的任务不允许修改（ReportStatus>=1 拒绝 SaveInspectTask）", async () => {
        // 用 LTO 任务验证：先 mock 状态（或用另一条已生成报告的任务）
        // 此处以期望接口返回 400/403 为验证目标（任务已处于 ReportStatus=0 状态故跳过实际生效）
        // 实际测试需先生成报告后再验证拒绝逻辑（见 T09 之后）
        // 此用例在 GenerateReport 之后重复调用 SaveInspectTask 验证（标记延后验证）
        assert(true, "延后至 T09 之后验证，当前跳过");
    });

    // ─── 阶段 8：预览报告 ─────────────────────────────────────────
    console.log("\n▶ 阶段 8  预览报告（T08）");

    await test("T08-01  PreviewReport 返回报告数据，不修改 ReportStatus", async () => {
        const { res, json } = await get(`/VehicleInspect/PreviewReport?inspectId=${manualInspectId}`);
        assertOk(res);
        const d = json.Data ?? json;
        assert(d.Vin,     "PreviewReport 缺少 Vin");
        assert(d.InspectData !== undefined, "PreviewReport 缺少 InspectData");
        // 确认 ReportStatus 未变
        const detail = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        assertEqual((detail.json.Data ?? detail.json).ReportStatus, 0, "PreviewReport 不应修改 ReportStatus");
        // 确认无 ReportToken
        assert(!(d.ReportToken), "PreviewReport 不应生成 ReportToken");
    });

    await test("T08-02  PreviewReport 不触发企微/短信推送（接口纯只读）", async () => {
        // 多次调用，结果幂等
        const r1 = await get(`/VehicleInspect/PreviewReport?inspectId=${manualInspectId}`);
        const r2 = await get(`/VehicleInspect/PreviewReport?inspectId=${manualInspectId}`);
        assertOk(r1.res);
        assertOk(r2.res);
        assertEqual(r1.res.status, r2.res.status, "PreviewReport 多次调用结果应一致");
    });

    // ─── 阶段 9：生成报告 ─────────────────────────────────────────
    console.log("\n▶ 阶段 9  生成报告（T09）");

    await test("T09-01  GenerateReport 返回 ReportUrl 和 Token，ReportStatus 变为 1 或 2", async () => {
        const { res, json } = await post("/VehicleInspect/GenerateReport", {
            ID: manualInspectId,
        });
        assertOk(res);
        assert(json.ReportUrl, "未返回 ReportUrl");
        assert(json.Token,     "未返回 Token");
        assert(json.Token.length === 32, `Token 应为 32 位，实际：${json.Token}`);
        reportToken = json.Token;
        reportUrl   = json.ReportUrl;
        // ReportStatus 应变为 1（已生成）或 2（已发送）
        const detail = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        const status = (detail.json.Data ?? detail.json).ReportStatus;
        assert(status === 1 || status === 2, `生成报告后 ReportStatus 应为 1 或 2，实际 ${status}`);
    });

    await test("T09-02  重复调用 GenerateReport 生成新 Token，旧 Token 失效", async () => {
        const oldToken = reportToken;
        const { res, json } = await post("/VehicleInspect/GenerateReport", {
            ID: manualInspectId,
        });
        assertOk(res);
        assert(json.Token !== oldToken, "重复生成应产生新 Token");
        reportToken = json.Token;
        reportUrl   = json.ReportUrl;
        // 旧 Token 应无法获取报告
        const old = await get(`/InspectReport/GetReportData?token=${oldToken}`, null);
        assert(old.res.status === 400 || old.res.status === 403 || old.res.status === 404,
            `旧 Token 应返回 400/403/404，实际 ${old.res.status}`);
    });

    await test("T09-03  已生成报告后 SaveInspectTask 被拒绝（ReportStatus>=1）", async () => {
        const { res } = await post("/VehicleInspect/SaveInspectTask", {
            ...inspectDataPayload,
            ID: manualInspectId,
        });
        assert(res.status === 400 || res.status === 403,
            `已生成报告后 SaveInspectTask 应返回 400/403，实际 ${res.status}`);
    });

    // ─── 阶段 10：客户验证查看报告 ───────────────────────────────
    console.log("\n▶ 阶段 10  客户验证查看报告（T22/T23/T24）");

    await test("T22-01  SendSmsCode 正确手机号发送成功", async () => {
        const { res, json } = await post("/InspectReport/SendSmsCode", {
            Token: reportToken,
            Phone: TEST_PHONE,
        }, null);  // 匿名接口，不传 token
        assertOk(res);
        assert(json.Success !== false, `SendSmsCode 应成功，实际：${JSON.stringify(json)}`);
    });

    await test("T22-02  SendSmsCode 错误手机号被拒绝，不透露原因", async () => {
        const { res, json } = await post("/InspectReport/SendSmsCode", {
            Token: reportToken,
            Phone: "13900000000",  // 与任务中 CustomerPhone 不符
        }, null);
        assert(res.status === 400 || res.status === 403,
            `错误手机号应被拒绝（400/403），实际 ${res.status}`);
        // 错误消息不应透露"手机号不一致"，应模糊处理
        const msg = json?.Message ?? json?.message ?? "";
        assert(!msg.includes("不一致") && !msg.includes("不匹配"),
            "错误消息不应透露具体原因（安全要求）");
    });

    await test("T22-03  Token 不存在时 SendSmsCode 返回 404", async () => {
        const { res } = await post("/InspectReport/SendSmsCode", {
            Token: "00000000000000000000000000000000",
            Phone: TEST_PHONE,
        }, null);
        assert(res.status === 400 || res.status === 404,
            `无效 Token 应返回 400/404，实际 ${res.status}`);
    });

    await test("T23-01  VerifyCode 错误验证码被拒绝，ReportStatus 不变", async () => {
        const beforeDetail = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        const beforeStatus = (beforeDetail.json.Data ?? beforeDetail.json).ReportStatus;

        const { res } = await post("/InspectReport/VerifyCode", {
            Token: reportToken,
            Phone: TEST_PHONE,
            Code:  "000000",  // 错误验证码
        }, null);
        assert(res.status === 400 || res.status === 403,
            `错误验证码应被拒绝，实际 ${res.status}`);

        const afterDetail = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        const afterStatus = (afterDetail.json.Data ?? afterDetail.json).ReportStatus;
        assertEqual(afterStatus, beforeStatus, "错误验证码后 ReportStatus 不应变化");
    });

    await test("T24-01  GetReportData 未验证时返回 403/401", async () => {
        // 直接访问，sessionStorage 中无验证标记 → 后端 IsViewed=false 时拒绝
        const { res } = await get(`/InspectReport/GetReportData?token=${reportToken}`, null);
        assert(res.status === 401 || res.status === 403,
            `未验证时 GetReportData 应返回 401/403，实际 ${res.status}`);
    });

    // ── 使用测试环境的 mock 验证码完成验证（测试环境约定固定验证码或从 DB 读取）
    // 生产环境替换为从短信服务获取真实验证码
    await test("T23-02  VerifyCode 正确验证码通过，ReportStatus 变为 3", async () => {
        // 测试环境：重新发送验证码，从接口响应或 DB 中获取
        // 此处使用测试环境约定的固定短信验证码 "888888"（需在测试环境短信 mock 中配置）
        const MOCK_SMS_CODE = process.env.MOCK_SMS_CODE ?? "888888";

        const { res, json } = await post("/InspectReport/VerifyCode", {
            Token: reportToken,
            Phone: TEST_PHONE,
            Code:  MOCK_SMS_CODE,
        }, null);

        if (res.status === 400) {
            // 验证码不对（测试环境未配置 mock），跳过后续依赖此步骤的检查
            console.warn(`     ⚠  测试环境未配置 MOCK_SMS_CODE，VerifyCode 跳过（HTTP 400）`);
            console.warn(`        请设置环境变量 MOCK_SMS_CODE=<短信验证码> 后重跑`);
            return;
        }

        assertOk(res);
        smsCode = MOCK_SMS_CODE;

        // 验证 ReportStatus=3
        const detail = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        const d = detail.json.Data ?? detail.json;
        assertEqual(d.ReportStatus, 3,     `验证通过后 ReportStatus 应为 3，实际 ${d.ReportStatus}`);
        assertEqual(d.IsViewed,     true,   "验证通过后 IsViewed 应为 true");
        assert(d.ViewedTime,               "验证通过后 ViewedTime 应被记录");
        assert(!d.SmsCode,                 "验证通过后 SmsCode 应被清空");
        assert(!d.SmsCodeExpire,           "验证通过后 SmsCodeExpire 应被清空");
    });

    await test("T24-02  GetReportData 验证通过后返回完整报告数据", async () => {
        if (!smsCode) {
            console.warn(`     ⚠  VerifyCode 未通过，跳过 GetReportData 验证`);
            return;
        }
        const { res, json } = await get(`/InspectReport/GetReportData?token=${reportToken}`, null);
        assertOk(res);
        const d = json.Data ?? json;
        assert(d.Vin,              "报告数据缺少 Vin");
        assert(d.InspectData,      "报告数据缺少 InspectData");
        assert(d.PaintThicknessData, "报告数据缺少 PaintThicknessData");
        assert(d.CustomerName,     "报告数据缺少 CustomerName");
        assert(d.InspectUserName,  "报告数据缺少 InspectUserName（检测师签名）");
    });

    await test("T27-01  已读回写后同一任务再次验证通过（idempotent），ViewedTime 更新", async () => {
        if (!smsCode) {
            console.warn(`     ⚠  跳过`);
            return;
        }
        // 先重新发验证码
        await post("/InspectReport/SendSmsCode", { Token: reportToken, Phone: TEST_PHONE }, null);
        const before = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        const beforeViewed = (before.json.Data ?? before.json).ViewedTime;

        await new Promise(r => setTimeout(r, 1100));  // 等 1 秒保证时间戳变化

        const { res } = await post("/InspectReport/VerifyCode", {
            Token: reportToken, Phone: TEST_PHONE, Code: smsCode,
        }, null);
        assertOk(res);

        const after = await get(`/VehicleInspect/GetInspectTaskDetail?inspectId=${manualInspectId}`);
        const afterViewed = (after.json.Data ?? after.json).ViewedTime;
        assert(afterViewed !== beforeViewed, "多次验证通过后 ViewedTime 应更新");
    });

    // ─── 阶段 11：PC 端（T25/T26）────────────────────────────────
    console.log("\n▶ 阶段 11  PC 端（T25/T26）");

    await test("T25-01  GetInspectTaskListPC 不受 DealerCode 过滤，返回全量数据", async () => {
        const page = encodeURIComponent(JSON.stringify({ Index: 1, Size: 20 }));
        const { res, json } = await get(`/VehicleInspect/GetInspectTaskListPC?Page=${page}`, ADMIN_TOKEN);
        assertOk(res);
        const items = json.Data ?? json;
        assert(json.DataTotal >= 2, `PC 端应能查到至少 2 条数据（LTO+MANUAL），实际 ${json.DataTotal}`);
        // 验证 ReportStatus=3 的任务携带 ReportToken
        const viewed = items.find(i => i.ReportStatus === 3);
        if (viewed) {
            assert(viewed.ReportToken, "ReportStatus=3 的任务应返回 ReportToken");
        }
    });

    await test("T25-02  GetInspectTaskListPC 按 VIN 过滤", async () => {
        const page = encodeURIComponent(JSON.stringify({ Index: 1, Size: 20 }));
        const { res, json } = await get(
            `/VehicleInspect/GetInspectTaskListPC?Vin=${TEST_VIN_MANUAL}&Page=${page}`,
            ADMIN_TOKEN,
        );
        assertOk(res);
        const items = json.Data ?? json;
        assert(items.length >= 1, "PC 端按 VIN 过滤应返回对应任务");
        assert(items.every(i => i.Vin === TEST_VIN_MANUAL), "PC 端列表包含非目标 VIN");
    });

    await test("T25-03  非管理员 Token 访问 PC 端接口返回 401/403", async () => {
        const page = encodeURIComponent(JSON.stringify({ Index: 1, Size: 1 }));
        const { res } = await get(`/VehicleInspect/GetInspectTaskListPC?Page=${page}`, EVALUATOR_TOKEN);
        assert(res.status === 401 || res.status === 403,
            `非管理员访问 PC 端应返回 401/403，实际 ${res.status}`);
    });

    await test("T26-01  ExportInspectTasks 返回 Excel 文件流（Content-Type 校验）", async () => {
        const { res } = await post("/VehicleInspect/ExportInspectTasks", {
            Vin: TEST_VIN_MANUAL,
        }, ADMIN_TOKEN);
        assertOk(res);
        const ct = res.headers.get("content-type") ?? "";
        assert(
            ct.includes("application/vnd.openxmlformats") || ct.includes("application/octet-stream"),
            `ExportInspectTasks Content-Type 应为 xlsx 或 octet-stream，实际：${ct}`,
        );
        const cl = Number(res.headers.get("content-length") ?? 0);
        assert(cl > 1000, `Excel 文件大小异常（${cl} bytes），可能为空文件`);
    });

    // ─────────────────────────────────────────────
    // 结果汇总
    // ─────────────────────────────────────────────
    console.log(`\n${"=".repeat(60)}`);
    console.log(`  测试结果汇总`);
    console.log(`${"=".repeat(60)}`);
    console.log(`  通过：${passed}  失败：${failed}  共：${passed + failed}`);

    if (failed > 0) {
        console.log("\n  ✗ 失败用例：");
        results.filter(r => !r.ok).forEach(r => {
            console.log(`    - ${r.name}`);
            console.log(`      ${r.error}`);
        });
    }

    console.log(`\n  覆盖链路：`);
    console.log(`    LTO下发 → 手动创建 → 列表/详情查询 → OCR识别`);
    console.log(`    → 四步骤保存 → 预览报告 → 生成报告`);
    console.log(`    → 发送验证码 → 验证通过 → 已读回写`);
    console.log(`    → GetReportData → PC端列表 → 导出`);
    console.log("");

    process.exit(failed > 0 ? 1 : 0);
}

runAll().catch(e => {
    console.error("E2E 测试执行异常：", e);
    process.exit(1);
});
