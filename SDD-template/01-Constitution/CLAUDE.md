# NBMS 项目 Claude 开发规则

## 项目概览

### 项目群结构

| 项目目录 | 类型 | 说明 |
|---------|------|------|
| `nbms` | .NET Framework 后端 | 主业务 API，IIS 端口 9002 |
| `nbms-ucm` | .NET Framework 后端 | UCM（二手车管理）API，IIS 端口 9003 |
| `nbms-admin` | Vue.js 前端 | 新业务系统管理后台 |
| `nbms-customer` | Vue.js 前端 | 尊享平台（经销商端） |
| `nbms-fleet-h5` | Vue.js 前端 | 沃世界 H5 |
| `nbms-usedcar-h5` | Vue.js 前端 | 企微二手车 H5 |
| `nbms-dataservice` | 后端服务 | 数据同步服务 |
| `nbms-ucl` | 后端服务 | UCL 服务 |
| `reportdatasync` | 后端服务 | 报表数据同步 |

### 系统与项目对应关系

| 系统名称 | 涉及项目 |
|---------|---------|
| 企微系统 | nbms-usedcar-h5 + nbms-ucm |
| 新业务系统 | nbms-admin + nbms |
| 内网拍 | nbms-ucm.admin |
| 尊享平台 | nbms-customer |
| 沃世界 | nbms-fleet-h5 + nbms |

### 本地路径

- 项目根目录：`D:\KPMG\nbms\`
- 主后端解决方案：`D:\nbms\nbms.sln`
- UCM 解决方案：`D:\nbms-ucm\nbms-UCM.sln`
- MSBuild：`D:\IDE\Visual Studio 2022\MSBuild\Current\Bin\MSBuild.exe`
- 接口文档输出：`D:\nbms-\docs\`
- 估点文档：`D:\nbms\估点\`

---

## 自定义技能 (Skills)

### 接口文档生成器 (/generate-api-doc)

**触发方式**：用户说"帮我写接口文档"、"写到md"、"生成API文档"，或粘贴包含URL和JSON的日志内容

**输出格式**：
- 文件路径：`D:\nbms\docs\{接口中文名}-{方法名}-接口文档.md`
- 包含：接口信息、请求参数、响应参数（按功能分组）、响应示例、枚举值说明

**详细规则**：参见 `.claude/skills/generate-api-doc.md`

---

### 后端编译发布 (/build-and-deploy)

**触发方式**：用户说"编译后端"、"重新编译"、"发布后端"、"重启后端"、"编译并发布"、"build"

**执行内容**：
1. MSBuild 编译 `D:\KPMG\nbms-\nbms-\nbms-.sln`（Debug 配置）
2. 编译成功后回收 IIS 应用池 `nbms-Api`
3. 验证站点状态，服务地址 `http://localhost:9002`

**详细规则**：参见 `.claude/skills/build-and-deploy/SKILL.md`

---

### UCM 后端编译发布 (/build-and-deploy-ucm)

**触发方式**：用户说"编译ucm"、"发布ucm"、"重启ucm"、"编译nbms-ucm"

**执行内容**：
1. MSBuild 编译 `nbms-UCM.Dealer.WebApi.csproj`（⚠️ 不要编译整个 sln，`NewBIeRocketMQService` 有证书签名问题）
2. 回收 IIS 应用池 `nbms-UCMApi`
3. 验证站点状态，服务地址 `http://localhost:9003`

**详细规则**：参见 `.claude/skills/build-and-deploy-ucm/SKILL.md`

---

### Git 项目状态查询 (/git-status)

**触发方式**：用户说"查看项目状态"、"git状态"、"各项目分支"

扫描全部 9 个项目，自动 pull 并生成状态报告，保存到 `D:\KPMG\nbms-\Git项目状态报告.md`

**详细规则**：参见 `.claude/skills/git-status/SKILL.md`

---

### 拉取开发分支 (/pull-dev-branch)

**触发方式**：用户说"拉取开发分支 feature-XXXXXXXX"、"基于 xxx 创建我的开发分支"

基于指定发版分支，在所有存在该分支的项目上创建 `dev-{发版分支}-damon` 并推送到远程。

**详细规则**：参见 `.claude/skills/pull-dev-branch/SKILL.md`

---

### PRD + 技术方案文档生成 (/prd-tech-design)

**触发方式**：用户说"帮我写PRD"、"生成技术方案"、"写需求文档"

完整文档工作流：需求分析 → PRD（业务语言）→ 技术方案（Mermaid 图）→ Jira 卡（可选）

⚠️ 需要 Chrome DevTools MCP 连接（`--remote-debugging-port=9222`）才能读取 Confluence 模板

**详细规则**：参见 `.claude/skills/prd-tech-design/skill.md`

---

### Jira Story 生成 (/generate-jira-story)

**触发方式**：用户提供功能简称 + JIRA卡号 + PRD/技术方案 Confluence 链接

输出 Confluence Wiki 格式（非 Markdown）的 Jira 卡内容，保存到 `D:\KPMG\nbms-\Jira卡-{卡号}-[{功能名}].md`

⚠️ 输出必须是 Confluence Wiki 格式：`h3.`、`{color:#XXXXXX}`、`* `、`| *Header* |`，**不能用 Markdown 语法**

**详细规则**：参见 `.claude/skills/generate-jira-story/SKILL.md`

---

### 测试用例生成 (/generate-test-cases)

**触发方式**：用户提供 Jira卡号 + 需求名称 + Confluence 链接

生成 Excel 格式测试用例，保存到 `D:\KPMG\nbms-\{需求名称}-测试用例.xlsx`

⚠️ 需要 Chrome DevTools MCP + excel-mcp-server（8017端口）

**详细规则**：参见 `.claude/skills/generate-test-cases/SKILL.md`

---

### AI Agent 估点 (/agent-estimation)

**触发方式**：用户说"帮我估点"、"生成估点表"，描述 Agent 需求

基于 Dify + LangChain 混合架构，输出含 BA/DL/Dev/QA 人天分配的标准估点表

**详细规则**：参见 `.claude/skills/agent-estimation/SKILL.md`

---

### 车型外观内饰 SQL 生成 (/insert-vehicle-exterior-interior)

**触发方式**：用户说"给我插入外观内饰 SQL"、"生成车型配置 SQL"

根据 P12Code、年款、外观颜色列表、内饰列表，生成写入 `PvUCM.dbo.CMN_VehicleExteriorInterior` 的 INSERT SQL

**详细规则**：参见 `.claude/skills/insert-vehicle-exterior-interior/SKILL.md`

---

## Git Commit Message 规范

GitLab 强制校验，提交时必须严格遵守。

### 格式

```
feat: [JIRA-ID]提交描述
```

### 规则

- `feat` / `fix` / `perf` 后面**必须**带 JIRA ID
- `docs` / `style` / `refactor` / `test` / `chore` / `ci` / `revert` 的 JIRA ID 可选
- 冒号后必须有一个空格：`feat: `
- JIRA ID 用方括号包裹：`[CVN-12697]`，多个用逗号分隔 `[CVN-001,CVN-002]`
- 描述不超过 72 个字符，**不能以句号结尾**

### Merge commit 格式

```
Merge branch 'source' into 'target'
```

⚠️ 两个分支名都必须用**单引号**包裹，必须是 `Merge branch`（不能是 `Merge remote-tracking branch`）

✅ 正确：`Merge branch 'dev-feature-biam-damon' into 'dev-feature-20260312-damon'`
❌ 错误：`Merge remote-tracking branch 'remotes/origin/xxx' into yyy`

### 示例

```
feat: [CVN-12697]增加BIAM登录日志
fix: [CVN-12697]修复补交逻辑异常
perf: [CVN-12697]优化返利提报查询性能
refactor: 重构EncryptHelper工具类
Merge branch 'dev-feature-biam-damon' into 'dev-feature-20260312-damon'
```

### Merge commit 格式修复

如果 Merge commit 消息不符合格式，用 filter-branch 修正后 force push：

```bash
git filter-branch -f --msg-filter '
msg=$(cat)
if echo "$msg" | grep -q "Merge remote-tracking branch.*foo.*into bar"; then
  echo "Merge branch '\''foo'\'' into '\''bar'\''"
else
  echo "$msg"
fi
' origin/target-branch..HEAD
git push --force origin branch-name
```

---

## 后端开发规则（.NET Framework）

### ⚠️ 新增 .cs 文件必须手动加入 csproj

`nbms-.Api` 使用 .NET Framework（旧格式 csproj），新建的 `.cs` 文件**不会自动被项目包含**，必须手动在 `.csproj` 中添加 `<Compile Include="..." />` 条目，否则编译时不会包含该文件，接口会返回 404。

每次在 `nbms-.Api` 项目下新建 `.cs` 文件后，在 `nbms-.Api.csproj` 中添加：

```xml
<Compile Include="Controllers\YourNewController.cs" />
```

找到同目录下相邻文件的 `<Compile>` 条目，在其后插入新条目。

**验证方法**：

```bash
grep "YourNewController" d:\KPMG\nbms-\nbms-\nbms-.Api\nbms-.Api.csproj
```

有输出才说明已正确包含。

---

### ⚠️ 数据库访问必须使用 EDMX（Entity Framework Database-First）

nbms-ucm 项目使用 **Database-First EF**，所有数据库操作必须通过 EDMX 生成的 `nbms-UCMEntities` DbContext，**不允许**使用 Code-First（`DbContext` 子类 + `OnModelCreating`）。

**原因**：项目已有完整的 EDMX 模型（`nbms-UCM.edmx`），Code-First 会绕过 EDMX 映射，导致连接字符串冲突（EDMX 连接字符串含 `metadata=` 前缀，Code-First 无法解析）。

**正确做法**：
1. 新建数据库表后，由**开发者手动在 Visual Studio 中更新 EDMX**（右键 `.edmx` → 从数据库更新模型）
2. EDMX 更新后会自动生成对应的实体类（`.tt` 模板生成）和 `DbSet` 注册
3. 代码中直接使用 `new nbms-UCMEntities()` 访问新表

**禁止**：
- 新建继承 `DbContext` 的子类（如 `VehicleInspectTaskContext`）
- 在代码中使用 `modelBuilder.Entity<T>().ToTable(...)` 等 Code-First 配置
- 在 Web.config 中新增纯 ADO.NET 连接字符串绕过 EDMX

**EDMX 更新流程**（由开发者在 Visual Studio 中操作）：
1. 在数据库执行建表 SQL
2. 打开 `nbms-UCM.Models\nbms-UCM.edmx`
3. 右键设计器空白处 → "从数据库更新模型"
4. 勾选新表 → 完成
5. 编译确认新实体类已生成

---



**不要习惯性地截断字符串**，除非确定这个字符串是入库的，且字段类型不为 `text`。

| 场景 | 字段 | 类型 | 处理 |
|------|------|------|------|
| 需要截断 | `BIAM_EventGrid_Log.ProcessMessage` | `nvarchar(500)` | 截断到 450 字符 |
| 不需要截断 | 日志输出（LogHelper.WriteInfo/WriteError） | - | 不截断 |
| 不需要截断 | API 响应消息 | - | 不截断 |
| 不需要截断 | 调试信息 | - | 不截断 |

---

## ⚠️ SQL 字符串字面量必须加 N 前缀

本项目数据库（PvUCM / Pvnbms）所有字符串字段均为 `NVARCHAR`，**所有 SQL 字符串字面量必须加 `N` 前缀**，否则中文字符入库后会变成乱码或问号。

### 规则

- **所有** `'...'` 形式的字符串字面量，只要值可能含中文（或不确定），一律写成 `N'...'`
- 包括：`INSERT VALUES`、`UPDATE SET`、`WHERE` 条件、`DEFAULT` 约束、`IF NOT EXISTS` 判断、`PRINT` 语句
- 纯英文/数字的字面量（如 `'MANUAL'`、`'skeleton'`）也建议加 `N`，保持一致性

### 示例

```sql
-- ❌ 错误
INSERT INTO VOV_DealerVehicleInspectCategory (Code, Name) VALUES ('skeleton', '骨架');
UPDATE SYS_Menu SET Title = '经销商收车检测' WHERE Name = 'usedcar-inspect-dealer';

-- ✅ 正确
INSERT INTO VOV_DealerVehicleInspectCategory (Code, Name) VALUES (N'skeleton', N'骨架');
UPDATE SYS_Menu SET Title = N'经销商收车检测' WHERE Name = N'usedcar-inspect-dealer';
```

### deploy.sql / 数据库变更脚本

每次写 SQL 脚本时，完成后必须全文检索 `'`，确认所有字符串字面量都已加 `N`。

**快速检查命令**：
```bash
# 找出所有未加N前缀的字符串字面量（排除注释行）
grep -n "[^N]'" deploy.sql | grep -v "^[[:space:]]*--"
```

---

## 前端开发规则（Vue.js）

### ⚠️ 动态路由组件注册位置

动态路由组件必须注册在 `src/utils/routehelper.js`，**不要**在 `src/router/generator-routers.js` 中注册。

**正确做法**：在 `src/utils/routehelper.js` 的 `constantRouterComponents` 对象中注册：

```javascript
const constantRouterComponents = {
  // 代步车活动
  'CustomerDaibuExamineList': () => import(/* webpackChunkName: "customer" */ '@/views/customer/daibu/ExamineList'),
  // 本地销售审核专项
  'LocalSalesAuditExamineList': () => import(/* webpackChunkName: "customer" */ '@/views/customer/localsales/ExamineList'),
}
```

**验证方法**：注册后重启开发服务器 `npm run serve`，清除浏览器缓存，在控制台执行：

```javascript
const app = document.querySelector('#app');
const vm = app.__vue__;
const route = vm.$route;
console.log('当前路由组件:', route.matched[route.matched.length - 1].components.default);
```

输出不是 `anonymous` 说明注册成功。

### 本地销售路由映射

| 路由 | 页面功能 |
|------|----------|
| `/customer/localsales/applylist` | 销售登记与提报 |
| `/customer/localsales/examinelist` | 返利审批 |
| `/customer/localsales/feedback` | 返利查询&反馈 |

---

## 飞书文档表格操作规则

### ⚠️ 禁止用 block_insert_after 向表格追加新行

**问题根因**：
- 以单元格内 `<p>` 节点为锚点时，新内容会被塞进该单元格，而不是新建一行
- 以表格自身 block ID 为锚点时，新内容会变成表格外的游离段落

### 正确做法：整表重建

需要追加行时，必须用 `block_replace` 替换整张表格，一次性写入包含所有行的完整内容：

```bash
# 先获取表格的 block ID
lark-cli docs +fetch --api-version v2 --doc "<url>" --scope section --start-block-id "<section-id>" --detail with-ids --as user
# 找到 <table id="..."> 的 ID，然后整表替换
lark-cli docs +update --api-version v2 --doc "<url>" --command block_replace \
  --block-id "<table-block-id>" \
  --content '<table>...(完整表格内容)...</table>' --as user
```

修改表格内**已有单元格**的内容时，用 `block_replace` 替换该单元格的 `<p>` block ID 是安全的。

**验证**：操作后必须用 `--doc-format markdown` 验证表格结构：

```bash
lark-cli docs +fetch --api-version v2 --doc "<url>" --scope section --start-block-id "<section-id>" --doc-format markdown --as user
```
