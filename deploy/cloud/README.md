# Pico 公网管理入口

更新：2026-09-21。当前入口：https://82.157.168.149/

## 当前安全边界
- 云端 Caddy 使用 Let's Encrypt IP 证书，自动续期；不需要域名或浏览器客户端证书。
- 管理页面公开，但管理业务 API 仍需有效的 Pico 管理员 Bearer token。
- 管理员账号为 pico；密码见本机 .runtime/admin-access.txt，不要提交或公开。
- 已按用户确认移除客户端证书认证；没有配置 strict_sni_host insecure_off。
- 内部配置、服务上报、诊断接口由 Caddy 拒绝，本地 Nginx 再做一层拦截。
- 登录端点使用全站共享限速：5 次/分钟的补充速率，允许首次短时连续 5 次，超额 HTTP 429。成功与失败均计数；不是按账号失败次数锁定。
- 管理 API 总体限速为 20 次/秒、burst 40。登录限速不信任客户端 IP 请求头，无法通过伪造 X-Forwarded-For 绕过；单管理员共享预算可能被外部请求耗尽。
- 管理 HTTP 跳转 HTTPS；原设备 HTTP WebSocket/OTA 路由保留兼容，不在本次强制迁移。

## 拓扑与部署
- 云端 127.0.0.1:18002 -> SSH 反向隧道 -> Mac 127.0.0.1:8002。
- Mac launch agent：~/Library/LaunchAgents/com.pico.manager-tunnel.plist，KeepAlive + 15 秒重试节流。
- 原设备隧道 18000/18003 不变。
- manager-api、MySQL、Redis 均无 Docker 宿主端口映射。
- 云端 Caddy admin 2019 和所有反向隧道端口只绑定回环地址。
- 云端配置 /etc/caddy/Caddyfile；本地副本 deploy/cloud/Caddyfile。
- 本地限速与第二层接口封锁：deploy/local/nginx.conf。

## 本次实际验证
- 公网 HTTPS 正常，无跳过证书校验；浏览器显示“Pico 管理员登录”及验证码。
- 公网根页面 HTTP 200；未登录 /pico/user/info 返回业务 code 401（HTTP 200 为现有 API 约定）。
- /pico/config/server-base、agent-models、编码路径 %63onfig、config;test 和 actuator 均返回 404。
- 连续 10 次空登录请求，前 5 次进入后端并被拒绝，后 5 次返回 HTTP 429。
- /pico/ota/ 返回 200。
- nginx -t、Caddy validate 通过，均已重载。
- 本次未重新执行正确密码的完整登录，也未进行真实固件刷入测试。

## 运维注意
- Mac 必须在线、不休眠；LaunchAgent 在用户登录后运行。未做强制断线重连测试。
- Caddy 已配置自动续期，但尚未观察完整续期周期。
- 云端另有既存 0.0.0.0:3000 Node 监听，本次未修改，不能声称整机仅开放 22/80/443。
- 旧客户端证书保留在 .runtime/cloud-access/，当前不再用于访问认证；不需要导入。
- 重载 Nginx 前须等待 Docker 文件挂载同步，并执行 docker exec pico-manager-web-1 nginx -t。

## 回退
- /etc/caddy/Caddyfile.before-admin-login 为移除客户端证书之前的配置（恢复后裸 IP 浏览器访问会再次受限）。
- /etc/caddy/Caddyfile.before-pico-management 为引入管理端前的配置。
- 回退配置必须先通过 caddy validate 再 reload；不要停止设备隧道或删除数据库卷。
