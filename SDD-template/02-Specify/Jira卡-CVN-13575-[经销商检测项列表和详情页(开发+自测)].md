h3. {color:#de350b}PO需求{color}

经销商二手车评估师目前没有一套系统化的工具来管理收车检测任务。评估师在完成收车检测后，任务信息分散，难以追溯历史检测记录，也无法快速定位某辆车的检测状态。本次需求是在企微 H5（nbms-usedcar-h5）中新增检测管理入口，使二手车评估师能够通过检测任务列表页按 VIN 查询历史任务，并进入任务详情页查看完整的检测信息。

本模块是整个收车检测功能的基础入口，仅二手车评估师角色可见（需在系统配置中加入角色控制），其他角色不展示该菜单。功能参考现有 UCL（二手车列表）模块的列表页风格和组件规范实现。

本卡为后端接口开发 + 前端列表/详情页开发 + 自测。

h3. {color:#00875a}用户故事{color}

* 用户/系统: 企业微信二手车 H5（nbms-usedcar-h5）+ project-v-ucm 后端 API

* 行为: 基于 03-经销商收车检测模块 PRD 及技术方案，在 nbms-usedcar-h5 新增检测管理列表页和任务详情页，在 project-v-ucm 新增 GetInspectTaskList、GetInspectTaskDetail 两个后端接口，实现二手车评估师对检测任务的查询和查看能力。

* 价值: 为评估师提供检测任务的统一管理入口，实现历史任务可追溯、任务状态可感知，提升检测业务的管理效率。

h3. {color:#ffab00}验收标准{color}

| *前置假设条件* | *业务行为举例* | *期望结果* |
| 评估师已登录企微 H5 | 评估师进入检测管理列表页 | 展示当前经销商下的检测任务列表，字段包含：任务编码、旧车 VIN、创建时间、任务状态（草稿/已生成/已发送/已查看） |
| 系统中无检测任务 | 评估师进入检测管理列表页 | 列表区域显示"暂无数据" |
| 有多条检测任务 | 评估师在列表页搜索框输入 VIN 关键字 | 列表实时过滤，仅展示 VIN 包含该关键字的任务 |
| 已有检测任务数据 | 评估师点击某条任务 | 进入任务详情页，展示车辆基本信息（VIN、品牌、车系、车型、车牌、里程）以及四步骤的完整录入内容 |
| 非二手车评估师角色登录 | 用户进入 H5 首页 | 菜单中不显示"检测管理"入口 |
| 后端接口未传入正确的 vehicleId | 前端调用 GetInspectTaskDetail | 后端返回错误信息，前端提示"检测任务不存在" |

h3. {color:#4c9aff}PRD文档{color}
{color:#4c9aff}[03-经销商收车检测模块 PRD - CED Technical Management Open Space - CEDTMOS - Confluence|https://confluence.project-v.internal/spaces/CEDTMOS/pages/347775363/03-经销商收车检测模块]{color}

h3. {color:#4c9aff}技术方案{color}
{color:#4c9aff}[03-经销商收车检测模块技术方案 - CED Technical Management Open Space - CEDTMOS - Confluence|https://confluence.project-v.internal/spaces/CEDTMOS/pages/347797253/03-%E7%BB%8F%E9%94%80%E5%95%86%E6%94%B6%E8%BD%A6%E6%A3%80%E6%B5%8B%E6%A8%A1%E5%9D%97%E6%8A%80%E6%9C%AF%E6%96%B9%E6%A1%88]{color}
