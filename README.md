# 安徽工业大学晚寝自动签到脚本 (AHUT Auto Sign-in)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

用于安徽工业大学（AHUT）学生考勤系统的自动化晚寝签到脚本。项目支持多用户并发签到、失败重试，以及签到结果邮件通知。

---

## 功能概览

- 自动完成签到全流程：登录、任务获取、提交签到。
- 多用户并发执行，支持批量签到。
- 内置重试机制，降低偶发网络波动影响。
- 配置文件独立：使用 `config.json` 管理参数，不需要改代码。
- 邮件通知：每位用户签到后都会发送结果邮件（成功/失败都会发）。

---

## 项目文件说明

- `main.py`：签到主程序。
- `config.example.json`：可提交到仓库的样板配置。
- `config.json`：本地真实配置（已在 `.gitignore` 忽略，不会上传）。

---

## 快速开始

### 1. 环境准备

- Python 3.8+
- 已克隆本仓库

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 生成本地配置

Linux/macOS:

```bash
cp config.example.json config.json
```

Windows PowerShell:

```powershell
Copy-Item .\config.example.json .\config.json
```

### 4. 编辑 `config.json`

至少填写以下字段：

- `users[].student_id`：学号（必填）
- `users[].password`：考勤系统密码
- `users[].email`：该用户接收通知的邮箱
- `email.sender_email`：发件邮箱
- `email.sender_password`：SMTP 密码/授权码

配置示例：

```json
{
  "log_level": "INFO",
  "debug": false,
  "max_retries": 4,
  "max_token_retries": 3,
  "max_workers": 20,
  "http_timeout_seconds": 10,
  "email": {
    "enabled": true,
    "account_type": "IMAP",
    "imap_server": "imap.exmail.qq.com",
    "imap_port": 993,
    "imap_ssl": true,
    "smtp_server": "smtp.exmail.qq.com",
    "smtp_port": 465,
    "use_ssl": true,
    "use_tls": false,
    "sender_name": "AHUT Auto Sign-In",
    "sender_email": "auto-sign-in@jorban.top",
    "sender_password": "YOUR_SMTP_PASSWORD"
  },
  "users": [
    {
      "student_id": 259000001,
      "password": "YOUR_AHUT_PASSWORD",
      "email": "user@example.com",
      "is_encrypted": 0,
      "latitude": 118.554951,
      "longitude": 31.675607
    }
  ]
}
```

### 5. 运行脚本

```bash
python main.py
```

说明：

- `debug=false` 时，仅在签到时间窗口内执行（代码默认校验 21:20 之后）。
- 需要白天联调时，可临时改为 `debug=true`。

---

## 邮件通知规则

- 无论签到成功或失败，都会发送邮件。
- 成功邮件标题：`签到成功`
- 失败邮件标题：`签到失败`
- 失败邮件正文：失败日志（包含时间、步骤、错误信息、重试信息）

---

## 自动化运行（进阶）

可通过系统定时任务每天自动执行：

- Linux/macOS：`crontab`
- Windows：任务计划程序
- GitHub Actions：可使用定时触发工作流

---

## 安全与提交规范

- `config.json` 包含账号、密码、邮箱配置，禁止提交到远程仓库。
- 仓库已在 `.gitignore` 忽略 `config.json`。
- 仅提交 `config.example.json` 作为公共样板。

---

## 常见问题

### 邮件发送失败

- 检查 `smtp_server`、`smtp_port`、`use_ssl` 是否正确。
- 检查 `sender_password` 是否为 SMTP 可用密码/授权码。
- 检查服务器网络是否允许访问 `smtp.exmail.qq.com:465`。

### 提示未到签到时间

- 这是正常保护逻辑。
- 如需联调，请将 `config.json` 中 `debug` 设置为 `true`。

---

## 免责声明

- 本项目仅供学习与技术交流使用。
- 请勿用于任何非法用途或商业活动。
- 学校系统接口可能变更，脚本有效性不作永久保证。
- 使用本项目产生的风险由使用者自行承担。

---

## 贡献

欢迎提交 Issue 或 Pull Request 来改进项目。
