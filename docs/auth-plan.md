# 登录注册接入方案

## 目标

- 为当前纪要产品增加简单可用的用户登录注册能力
- 优先支持国内可落地的邮箱注册 / 邮箱登录
- 尽量少改现有 `Python + 静态 HTML` 结构
- 为后续多用户数据隔离留出扩展空间

## 当前项目现状

- 前端是单页静态页面：`web/index.html`
- 后端是轻量 Python HTTP 服务：`src/server.py`
- 当前接口没有登录态：
  - `GET/POST /api/config`
  - `GET/POST/DELETE /api/minutes`
  - `POST /api/generate`
- 当前配置和数据都是全局读写，不区分用户

这意味着如果直接加一个“登录页”而不改存储层，只能做到“有人能进页面”，不能做到“不同用户的数据彼此隔离”。

## 需求拆解

本次建议按两层目标实施：

### 第一层：账号能力

- 邮箱注册
- 邮箱登录
- 登录态保持
- 退出登录
- 忘记密码

### 第二层：多用户隔离

- 每个用户只能看到自己的纪要列表
- 每个用户只能修改和删除自己的纪要
- 模型配置不能再是全局共享

如果只做第一层，产品只是“有登录入口”；如果要给别人长期使用，建议至少把第二层一起做掉。

## GitHub 备选项目

### 方案 A：PocketBase

- GitHub: [pocketbase/pocketbase](https://github.com/pocketbase/pocketbase)
- JS SDK: [pocketbase/js-sdk](https://github.com/pocketbase/js-sdk)
- 特点：
  - 单文件后端，部署很轻
  - 自带用户系统、管理后台、SQLite
  - 原生支持邮箱密码登录
  - 提供 REST API 和 JS SDK
  - 很适合当前这种轻量自建项目

适配度判断：

- 对当前项目最友好
- 不要求把 Python 服务整体重写
- 可以先把认证和用户数据托管给 PocketBase
- 现有页面可以直接通过 SDK 或 REST 接入

### 方案 B：Appwrite

- GitHub: [appwrite/appwrite](https://github.com/appwrite/appwrite)
- 特点：
  - 功能完整，认证能力成熟
  - 邮箱密码登录支持好
  - 还带数据库、存储、函数等能力

适配度判断：

- 能用，但对当前项目偏重
- 更适合从一开始就按完整 BaaS 方式建设
- 运维成本和学习成本都高于 PocketBase

### 方案 C：Casdoor

- GitHub: [casdoor/casdoor](https://github.com/casdoor/casdoor)
- 特点：
  - 国内团队背景，中文资料相对友好
  - IAM 能力强，支持很多协议和企业场景

适配度判断：

- 偏身份平台，不是最轻量方案
- 对这个 MVP 来说有些过度设计

## 推荐结论

推荐优先使用 **PocketBase**。

原因：

- 最符合当前项目“轻后端 + 静态前端”的结构
- 上手快，部署成本低
- 邮箱登录注册是内置能力
- 后续可以顺手把纪要数据也迁到 PocketBase，形成真正的多用户

## 推荐落地方式

建议采用：

`现有 Python 纪要生成服务 + PocketBase 负责认证和用户数据`

### 职责划分

PocketBase 负责：

- 用户注册
- 用户登录
- 用户会话
- 用户表
- 纪要数据表
- 用户级模型配置表

现有 Python 服务负责：

- 逐字稿清洗、分类、生成、校验
- 纪要渲染
- 业务规则校验

## 系统结构

```text
浏览器
  -> PocketBase（注册 / 登录 / 用户鉴权）
  -> 现有 Python 服务（生成纪要）
  -> PocketBase（保存纪要、读取纪要）
```

## 两种接入路径

### 路径 1：最小改造

- 前端直接接 PocketBase 登录
- 登录成功后，前端拿到用户 token
- 纪要列表和配置改为直接访问 PocketBase
- 生成时，前端把用户 token 带给 Python 服务
- Python 服务只负责生成，并根据 token 校验用户身份

优点：

- 改造速度快
- 前端改动相对集中

缺点：

- 前端要同时调用两个服务
- Python 服务要增加 token 校验逻辑

### 路径 2：后端代理式接入

- 前端只调用现有 Python `/api/*`
- Python 服务代为请求 PocketBase 完成注册、登录、读写用户数据
- 登录态通过 Python 自己的 Cookie 维护

优点：

- 前端改动更少
- 对外只有一个业务域名

缺点：

- Python 侧要多写一层认证代理
- 实现量比路径 1 更大

## 本项目推荐的实施路径

推荐 **路径 1**。

原因：

- 当前前端就是纯 HTML + JS，直接接 SDK 很自然
- 当前 Python 服务非常轻，不适合先做一大层会话系统
- 更容易快速上线第一版

## 数据模型建议

### 1. users

PocketBase 自带 auth collection，直接使用。

字段建议：

- `email`
- `password`
- `name`

### 2. minutes

新增纪要集合。

字段建议：

- `owner`：关联用户
- `title`
- `status`
- `input_kind`
- `source_input`
- `transcript_json`
- `minutes_json`
- `markdown`
- `document_html`
- `created`
- `updated`

规则建议：

- 仅登录用户可创建
- 仅 `owner = @request.auth.id` 可读写删

### 3. model_configs

不要继续沿用全局 `.minutes.config.json` 给多用户共用。

建议新增集合：

- `owner`：关联用户
- `provider`
- `model`
- `base_url`
- `api_key_encrypted` 或服务端代存字段
- `temperature`
- `max_tokens`
- `timeout_seconds`

规则建议：

- 用户只能访问自己的配置

## 接口改造建议

### 前端新增

- 登录页 / 弹窗
- 注册页 / 弹窗
- 忘记密码入口
- 顶部用户信息和退出按钮

### 前端替换

当前这些接口建议从“全局接口”改成“用户态接口”：

- `/api/minutes`
- `/api/minutes/:id`
- `/api/config`

### 后端新增

Python 服务建议新增：

- `POST /api/generate`
  - 校验用户登录态
  - 按用户读取模型配置
  - 生成后按用户保存结果

## 邮件能力建议

邮箱注册本身并不复杂，难点在发信。

建议：

- 测试期先用 SMTP 发信
- 正式期再切换到稳定的邮件服务商

可选方式：

- 企业邮箱 SMTP
- 腾讯企业邮 SMTP
- 阿里云邮件推送
- Resend

如果第一版想尽快上线，也可以先采用：

- 邮箱 + 密码注册
- 注册后不强制邮箱验证

等产品稳定后，再补邮箱验证和找回密码邮件。

## 分阶段实施建议

### 阶段 1：最小可用登录

- 部署 PocketBase
- 创建 `users`、`minutes`、`model_configs`
- 前端接入登录注册
- 登录后只显示当前用户数据
- Python 生成接口增加登录态校验

目标：

- 别人可以注册账号
- 登录后只看到自己的纪要

### 阶段 2：补齐账号体验

- 忘记密码
- 邮箱验证
- 退出登录
- 未登录访问拦截

### 阶段 3：生产化

- HTTPS
- 域名
- 数据备份
- API key 加密存储
- 基础限流

## 风险提醒

### 风险 1：只做登录，不做数据隔离

这样会出现：

- A 用户能看到 B 用户的纪要
- 全局模型配置互相覆盖

这是最需要避免的。

### 风险 2：把第三方 token 直接当业务权限结束

仍然需要在 Python 侧校验：

- 当前请求属于哪个用户
- 这个用户能否访问目标纪要
- 这个用户应该使用哪份模型配置

### 风险 3：API key 存储

如果允许每个用户配置自己的模型 key，就不能继续明文共享为全局配置。

## 结论

对于当前项目，最有性价比的方案是：

- 认证选 **PocketBase**
- 方式选 **前端直连 PocketBase + Python 保留生成服务**
- 范围上至少同时完成：
  - 邮箱注册登录
  - 用户纪要隔离
  - 用户模型配置隔离

这条路线改造量可控，也最符合当前项目结构。
