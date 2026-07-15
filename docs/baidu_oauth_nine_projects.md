# 九项目 / 十一超管百度 OAuth 授权清单

> 当前状态：服务商开发资格审核中。本页仅用于授权准备、只读探测和模拟验证；正式小时报/日报仍使用浏览器抓数。

## 迁移范围

九个项目全部迁移：长沙牛、昆明牛、南京白、南京牛、宁波牛、青岛白、沈阳白、沈阳牛、深圳白。

OAuth 必须按超管分别授权。其他 7 个项目各有 1 个超管；沈阳白有 2 个超管，沈阳牛有 2 个超管，因此总计需要 11 次授权。沈阳四个来源不得共用令牌。

## 部署前

1. 此前应用密钥和令牌曾用于调试。正式批量授权前，在百度应用管理中重置 secretKey。
2. 重置后更新腾讯云函数环境变量 `BAIDU_SECRET_KEY`。
3. 从百度应用管理的“查看授权链接”中复制 `state` 参数，填入 `BAIDU_ALLOWED_STATES`。
4. 保持现有回调地址不变。
5. 上传 `cloud/baidu_oauth_callback/dist/baidu_oauth_callback_scf.zip`。
6. 访问回调 URL，确认返回 `{"status":"ready"}`。

## 授权顺序

| 顺序 | 项目 | 本地 API profile |
| --- | --- | --- |
| 1 | 昆明牛 | `kunming_niu_baidu` |
| 2 | 长沙牛 | `changsha_niu_baidu` |
| 3 | 南京牛 | `nanjing_niu_baidu` |
| 4 | 宁波牛 | `ningbo_niu_baidu` |
| 5 | 青岛白 | `qingdao_bai_baidu` |
| 6 | 南京白 | `nanjing_bai_baidu` |
| 7 | 深圳白 | `shenzhen_bai_baidu` |
| 8 | 沈阳白来源 A（大中亚） | `shenyang_bai_source_a_baidu` |
| 9 | 沈阳白来源 B（大银康） | `shenyang_bai_source_b_baidu` |
| 10 | 沈阳牛中亚 | `shenyang_niu_zhongya_baidu` |
| 11 | 沈阳牛银康 | `shenyang_niu_yinkang_baidu` |

沈阳四个来源每次授权后，都必须核对返回的超管名称和子账户列表，只允许写入对应来源的 API profile。若来源归属不明确，程序应停止迁移并输出诊断，不能猜测映射。

每次操作：

1. 使用无痕窗口打开同一个应用授权链接。
2. 登录对应超管，不要登录子账户。
3. 同意授权并下载 `.baidu-auth` 文件。
4. 立即在本机导入，确认子账户数量和项目推广 ID。
5. 删除下载目录中的 `.baidu-auth` 文件。

导入命令：

```cmd
.venv\Scripts\python.exe main.py --mode import-baidu-oauth --file "下载的授权文件.baidu-auth" --api-profile changsha_niu_baidu
```

不要把授权文件、accessToken、refreshToken、secretKey 或百度密码发送到聊天工具。

## 切换正式 API 前的门槛

1. 服务商开发资格审核通过。
2. 九项目十一超管授权全部完成，并逐个确认超管主体、子账户和推广 ID 映射。
3. 沈阳牛、沈阳白的双来源分别取数后合并校验，不允许共用令牌或漏掉任一来源。
4. API 与浏览器在相同日期、相同时段连续对账通过。
5. 先单项目灰度，并保留浏览器回退；未通过验收的项目继续走浏览器。
