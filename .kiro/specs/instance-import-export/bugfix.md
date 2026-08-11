# Bugfix Requirements Document

## Introduction

当前实例管理系统缺少批量导入/导出功能，导致用户在跨环境部署时必须手动逐个创建实例配置，效率极低且容易出错。本修复将为实例管理添加 JSON 格式的导入/导出功能，支持安全的配置迁移。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户需要将实例配置迁移到新的部署环境 THEN 系统没有提供任何导出功能，用户只能手动记录每个实例的配置信息

1.2 WHEN 用户拥有多个实例配置需要在新环境中批量创建 THEN 系统没有提供任何导入功能，用户只能逐个手动创建实例

1.3 WHEN 用户希望在导出时保护 api_key 安全 THEN 系统没有任何导出机制，无法提供安全选项让用户选择是否包含敏感信息

1.4 WHEN 用户导入的 JSON 文件中存在与现有实例同名的记录 THEN 系统没有导入功能，无法处理名称冲突的情况

1.5 WHEN 用户只需要导出或导入部分实例 THEN 系统没有提供选择性导出/导入的能力，无法按需操作

### Expected Behavior (Correct)

2.1 WHEN 用户点击"导出"按钮 THEN 系统 SHALL 弹出导出对话框，展示所有实例列表供用户勾选要导出的实例，默认全选

2.2 WHEN 用户在导出对话框中选择部分实例并确认导出 THEN 系统 SHALL 仅导出被选中的实例配置为 JSON 文件并触发浏览器下载，默认包含 name、endpoint、deployment、type、description 字段，不包含 api_key

2.3 WHEN 用户在导出对话框中勾选"包含 API Key"选项后确认导出 THEN 系统 SHALL 在导出的 JSON 文件中包含 api_key 字段（明文）

2.4 WHEN 用户点击"导入"按钮并选择有效的 JSON 文件 THEN 系统 SHALL 解析文件内容并展示预览列表，显示将要导入的实例名称、类型、端点等信息，用户可勾选要导入的实例（默认全选）

2.5 WHEN 用户在导入预览中取消勾选某些实例后确认导入 THEN 系统 SHALL 仅批量创建被选中的实例配置，对于 JSON 中未包含 api_key 的实例，要求用户在导入前补填 api_key

2.6 WHEN 用户导入的实例名称与现有实例名称冲突 THEN 系统 SHALL 提供"跳过"或"更新"两种策略让用户选择，跳过则忽略该条记录，更新则覆盖现有实例配置

2.7 WHEN 用户选择导入的 JSON 文件格式无效或缺少必填字段 THEN 系统 SHALL 显示明确的错误提示，说明哪些字段缺失或格式不正确

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户通过"新建实例"按钮手动创建单个实例 THEN 系统 SHALL CONTINUE TO 正常创建实例并返回 201 状态码

3.2 WHEN 用户编辑或删除已有实例 THEN 系统 SHALL CONTINUE TO 正常执行更新/删除操作

3.3 WHEN 用户通过实例列表查看实例详情 THEN 系统 SHALL CONTINUE TO 显示脱敏的 api_key 和使用统计信息

3.4 WHEN 用户按类型筛选实例列表 THEN 系统 SHALL CONTINUE TO 正确过滤并展示对应类型的实例

3.5 WHEN 用户批量选择实例后执行删除 THEN 系统 SHALL CONTINUE TO 正常执行批量删除操作
