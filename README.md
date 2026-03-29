# AHUT Auto Sign-In

用于安徽工业大学考勤系统晚寝签到的自动化脚本。

## 功能概览

- 多用户签到（支持并发执行）
- 签到时间范围随机调度（`sign_time_window`）
- 非管理员用户先签到，管理员最后签到
- 普通用户签到完成后立即发送个人结果邮件
- 管理员接收一封“管理员结果 + 全员汇总”邮件
- 邮件主题与正文使用中文，签到开启/结果使用 Emoji 展示
- 常驻循环运行：当天完成后等待次日窗口继续执行
- 当天防重：同一天只执行一轮，避免重复签到
- 运行日志按年/月/日落盘

## 项目结构

- `app.py`：程序入口（常驻模式）
- `main.py`：签到核心脚本（由 `app/main_adapter.py` 反射调用）
- `app/`：核心业务模块
  - `runner.py`：总调度（随机时间、并发、跨日循环、防重复）
  - `main_adapter.py`：对 `main.py` 的兼容调用层
  - `email_service.py`：邮件模板与发送（中文 + Emoji）
  - `config.py`：配置加载与校验
  - `scheduler.py`：时间窗口与计划调度
  - `state_store.py`：当天防重状态持久化
  - `logging_setup.py`：控制台 + 文件日志
- `config.example.json`：配置模板
- `logs/`：日志目录（自动创建年月子目录）

## 环境要求

- Python 3.8+
- 依赖：`requests`、`aiohttp`

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置文件

先复制模板：

```bash
cp config.example.json config.json
```

Windows PowerShell：

```powershell
Copy-Item .\config.example.json .\config.json
```

### 关键配置项

```json
{
  "debug": false,
  "max_retries": 4,
  "max_token_retries": 3,
  "max_workers": 20,
  "http_connect_timeout_seconds": 3,
  "http_read_timeout_seconds": 10,
  "http_request_retries": 2,
  "http_retry_backoff_seconds": 1.0,
  "sign_time_window": {
    "start": "21:20:00",
    "end": "22:00:00"
  },
  "users": [
    {
      "student_id": 229000001,
      "username": "张三",
      "password": "YOUR_AHUT_PASSWORD",
      "is_encrypted": 0,
      "enabled": true,
      "latitude": 118.554951,
      "longitude": 31.675607,
      "email": "user@example.com"
    }
  ]
}
```

说明：

- `users[0]` 视为管理员账号。
- 普通用户会在 `sign_time_window.start ~ sign_time_window.end` 内随机时间签到。
- 当普通用户全部完成后，管理员最后签到并接收汇总邮件。
- `http_timeout_seconds` 仍兼容（未配置新字段时可作为读超时兜底）。

## 运行签到

```bash
python app.py
```

说明：

- 程序会常驻运行，不会在单次执行后退出。
- 当天签到完成后会输出次日预计签到时间，并等待到次日窗口。
- 防重复状态保存在 `logs/run_state.json`。
- 签到执行优先调用 `main.py` 的 `sign_in()`，必要时回退到 `main()` 以适配更新。

## 日志输出

- 控制台实时输出
- 文件日志输出到：

```text
logs/YYYYMM/YYYY-MM-DD.log
```

例如：

```text
logs/202603/2026-03-11.log
```

## 邮件规则

- 普通用户：签到任务结束后立即发送结果邮件
- 管理员：最后签到，发送一封包含
  - 管理员签到结果（🛡️）
  - 全员签到汇总表（📊）
- 主题与正文为中文；“签到开启/签到结果”使用 Emoji 状态展示（如：🟢/⚪、✅/❌）

## 安全注意

- `config.json` 含账号与邮箱凭据，禁止提交到远程仓库。
- 仓库已通过 `.gitignore` 忽略 `config.json` 与日志文件。

## 免责声明

本项目仅供学习与技术交流使用，请遵守学校及相关平台规范。
