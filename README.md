# AHUT Auto Sign-In

用于安徽工业大学考勤系统晚寝签到的自动化脚本。

## 功能概览

- 多用户签到（支持并发执行）
- 签到时间范围随机调度（`sign_time_window`）
- 非管理员用户先签到，管理员最后签到
- 普通用户签到完成后立即发送个人结果邮件
- 管理员接收一封“管理员结果 + 全员汇总”邮件
- 交互式用户管理脚本（自动保存）
- 运行日志按年/月/日落盘

## 项目结构

- `main.py`：程序入口
- `app/`：核心业务模块
  - `runner.py`：总调度（随机时间、并发、管理员最后执行）
  - `workflow.py`：签到流程（分步调用接口、重试）
  - `email_service.py`：邮件模板与发送
  - `config.py`：配置加载与校验
  - `logging_setup.py`：控制台 + 文件日志
- `manage_users.py`：交互式用户管理
- `config.example.json`：配置模板
- `logs/`：日志目录（自动创建年月子目录）

## 环境要求

- Python 3.8+

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
  "http_timeout_seconds": 10,
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

## 交互式管理用户

运行：

```bash
python manage_users.py
```

交互行为：

- 每次询问前会清空终端并展示当前用户列表。
- 每次新增/编辑/删除/启用状态切换后会自动保存到 `config.json`。
- 菜单项：
  - `2` 新增用户
  - `3` 编辑用户
  - `4` 删除用户
  - `5` 切换启用/禁用
  - `7` 仅退出

## 运行签到

```bash
python main.py
```

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
  - 管理员签到结果
  - 全员签到汇总表

## 安全注意

- `config.json` 含账号与邮箱凭据，禁止提交到远程仓库。
- 仓库已通过 `.gitignore` 忽略 `config.json` 与日志文件。

## 免责声明

本项目仅供学习与技术交流使用，请遵守学校及相关平台规范。

