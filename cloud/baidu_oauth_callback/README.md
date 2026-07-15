# 百度 OAuth 腾讯云 SCF 回调

当前已审核地址对应腾讯云 Python 3.6 Web 函数。部署包同时支持 Web 函数和普通 SCF 事件函数。

Web 函数部署配置：

- 运行环境：Python 3.6。
- 代码包：上传 `dist/baidu_oauth_callback_scf.zip`。
- 启动文件：压缩包根目录的 `scf_bootstrap`。
- 监听端口：9000，由 `app.py` 的 Python 标准库 WSGI 服务处理，不依赖 Flask。
- 健康检查：根路径和 `/baidu/oauth/callback` 无参数访问时都返回 `status=ready`。

若新建普通事件函数，配置为：

- 运行环境：Python 3.6。
- 执行入口：`index.main_handler`。
- 内存：256 MB 或以上。
- 超时：30 秒。
- 使用函数 URL 或 API 网关公开 HTTPS 触发器。
- 不记录请求参数、响应正文或完整事件。

必须保持已审核回调路径：

```text
/baidu/oauth/callback
```

腾讯云的函数日志和 API 网关访问日志不要开启完整查询参数记录，避免一次性 `authCode` 进入日志。

环境变量：

```text
BAIDU_APP_ID=百度应用 ID
BAIDU_SECRET_KEY=百度应用 secretKey
BAIDU_ALLOWED_STATES=授权链接中的 state；多个值用英文逗号分隔
BAIDU_MAX_TIMESTAMP_SKEW_SECONDS=600
```

部署包由项目根目录执行下面的命令生成：

```cmd
.venv\Scripts\python.exe tools\build_baidu_oauth_scf.py
```

生成位置：

```text
cloud/baidu_oauth_callback/dist/baidu_oauth_callback_scf.zip
```

授权成功后浏览器会下载一个 `.baidu-auth` 文件。该文件包含敏感令牌，只能在本机导入，不要发送、截图或上传到聊天工具。导入完成后应人工删除下载文件。
