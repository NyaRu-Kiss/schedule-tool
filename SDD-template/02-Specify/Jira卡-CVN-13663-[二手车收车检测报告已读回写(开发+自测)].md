h3. {color:#de350b}PO需求{color}

当客户通过手机号验证成功查看检测报告后，系统需要自动将该检测任务的状态更新为"已查看"，并记录客户的查看时间。这一状态回写机制为评估师和业务管理人员提供了客户行为的可见性，使其能够了解客户是否已查看报告，从而决定是否需要进行后续跟进。

已读状态回写是在客户验证通过的同一个接口调用中完成的，无需客户额外操作。回写完成后，评估师在检测任务列表中可以看到该任务状态变更为"已查看"，并可查看具体的查看时间。此外，GetReportData 接口在返回报告数据前会校验客户是否已完成验证（IsViewed 字段），未验证的请求将被拒绝，防止绕过验证直接获取报告数据。

本卡为后端 VerifyCode 接口中的状态回写逻辑 + GetReportData 接口的验证校验逻辑开发 + 自测。

h3. {color:#00875a}用户故事{color}

* 用户/系统: project-v-ucm 后端 API（VerifyCode 接口 + GetReportData 接口）

* 行为: 基于 03-经销商收车检测模块 PRD 及技术方案，在 project-v-ucm 的 VerifyCode 接口中实现验证通过后的已读状态回写（IsViewed=true、ViewedTime、ReportStatus=3），在 GetReportData 接口中实现 IsViewed 校验逻辑，确保只有已验证的客户才能获取报告数据。

* 价值: 实现客户已读状态的自动追踪，为评估师提供客户行为数据，支持后续业务跟进决策；同时通过接口层校验保障报告数据的访问安全性。

h3. {color:#ffab00}验收标准{color}

| *前置假设条件* | *业务行为举例* | *期望结果* |
| 客户完成手机号+验证码验证 | 客户点击"确认"验证通过 | 数据库中该检测任务的 IsViewed 更新为 true，ViewedTime 记录当前时间，ReportStatus 更新为 3（已查看） |
| 客户验证通过后 | 评估师在检测任务列表查看该任务 | 任务状态显示为"已查看"，可查看具体查看时间 |
| 客户验证通过，sessionStorage 有验证标记 | 客户刷新报告页，前端调用 GetReportData | 接口正常返回报告数据（IsViewed=true，校验通过） |
| 未经验证的请求 | 直接携带 token 调用 GetReportData 接口 | 接口返回错误（IsViewed=false），前端跳转至验证页 |
| 验证码校验失败 | 客户输入错误验证码 | IsViewed 不更新，ViewedTime 不记录，ReportStatus 不变 |
| 同一任务客户多次打开链接并验证 | 客户第二次验证通过 | ViewedTime 更新为最新查看时间，IsViewed 保持 true，ReportStatus 保持 3 |
| 验证通过后 SmsCode 处理 | 验证成功后查看数据库 | SmsCode 字段被清空，SmsCodeExpire 被清空，防止验证码被重复使用 |

h3. {color:#4c9aff}PRD文档{color}
{color:#4c9aff}[03-经销商收车检测模块 PRD - CED Technical Management Open Space - CEDTMOS - Confluence|https://confluence.project-v.internal/spaces/CEDTMOS/pages/347775363/03-经销商收车检测模块]{color}

h3. {color:#4c9aff}技术方案{color}
{color:#4c9aff}[03-经销商收车检测模块技术方案 - CED Technical Management Open Space - CEDTMOS - Confluence|https://confluence.project-v.internal/spaces/CEDTMOS/pages/347797253/03-%E7%BB%8F%E9%94%80%E5%95%86%E6%94%B6%E8%BD%A6%E6%A3%80%E6%B5%8B%E6%A8%A1%E5%9D%97%E6%8A%80%E6%9C%AF%E6%96%B9%E6%A1%88]{color}
