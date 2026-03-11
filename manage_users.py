import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_PASSWORD = "Ahgydx@920"
DEFAULT_LATITUDE = 118.554951
DEFAULT_LONGITUDE = 31.675607


def load_config(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8-sig") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object")

    users = config.get("users", [])
    if not isinstance(users, list):
        raise ValueError("config.users must be a list")

    return config


def save_config(path: Path, config: Dict) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")


def user_student_id(user: Dict) -> int:
    value = user.get("student_id", user.get("student_Id"))
    if value is None:
        return 0
    return int(value)


def normalize_user(user: Dict) -> Dict:
    normalized = dict(user)
    normalized["student_id"] = user_student_id(user)
    normalized.pop("student_Id", None)

    normalized.setdefault("username", "")
    normalized.setdefault("password", DEFAULT_PASSWORD)
    normalized.setdefault("is_encrypted", 0)
    normalized.setdefault("enabled", True)
    normalized.setdefault("latitude", DEFAULT_LATITUDE)
    normalized.setdefault("longitude", DEFAULT_LONGITUDE)
    normalized.setdefault("email", "")

    return normalized


def clear_terminal() -> None:
    # True clear only works in interactive terminals.
    if not sys.stdout.isatty():
        return

    if os.name == "nt":
        os.system("cls")
        return

    # Prefer clear when TERM exists, fallback to ANSI escape.
    if os.environ.get("TERM"):
        if os.system("clear") == 0:
            return

    # ANSI fallback for terminals without TERM but supporting escape sequences.
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def list_users(users: List[Dict]) -> None:
    print("当前用户列表")
    print("-" * 80)
    if not users:
        print("(空)")
        return

    for idx, user in enumerate(users, start=1):
        sid = user_student_id(user)
        name = user.get("username", "")
        enabled = "启用" if bool(user.get("enabled", True)) else "禁用"
        email = user.get("email", "")
        print(f"{idx}. 学号={sid} 姓名={name} 状态={enabled} 邮箱={email}")


def render_prompt(users: List[Dict], header: str = "") -> None:
    clear_terminal()
    list_users(users)
    print("-" * 80)
    if header:
        print(header)
        print("-" * 80)


def prompt_text(users: List[Dict], label: str, default: Optional[str] = None, header: str = "") -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    render_prompt(users, header)
    value = input(f"{label}{suffix}: ").strip()
    if value == "" and default is not None:
        return str(default)
    return value


def prompt_int(users: List[Dict], label: str, default: Optional[int] = None, header: str = "") -> int:
    error_message = ""
    while True:
        merged_header = f"{header}\n\n{error_message}" if error_message else header
        raw = prompt_text(users, label, None if default is None else str(default), merged_header)
        try:
            return int(raw)
        except ValueError:
            error_message = "请输入整数。"


def prompt_float(users: List[Dict], label: str, default: Optional[float] = None, header: str = "") -> float:
    error_message = ""
    while True:
        merged_header = f"{header}\n\n{error_message}" if error_message else header
        raw = prompt_text(users, label, None if default is None else str(default), merged_header)
        try:
            return float(raw)
        except ValueError:
            error_message = "请输入数字。"


def prompt_bool(users: List[Dict], label: str, default: bool = True, header: str = "") -> bool:
    default_text = "y" if default else "n"
    error_message = ""
    while True:
        merged_header = f"{header}\n\n{error_message}" if error_message else header
        raw = prompt_text(users, f"{label} (y/n)", default_text, merged_header).lower()
        if raw in ("y", "yes", "1", "true"):
            return True
        if raw in ("n", "no", "0", "false"):
            return False
        error_message = "请输入 y 或 n。"


def choose_user_index(users: List[Dict], action_name: str) -> Optional[int]:
    if not users:
        prompt_text(users, "用户列表为空，按回车返回", header=f"{action_name}失败")
        return None

    error_message = ""
    while True:
        header = f"{action_name}用户"
        if error_message:
            header = f"{header}\n\n{error_message}"
        raw = prompt_text(users, f"请输入序号(1-{len(users)}), 输入 q 返回", header=header)
        if raw.lower() == "q":
            return None
        try:
            index = int(raw)
            if 1 <= index <= len(users):
                return index - 1
        except ValueError:
            pass
        error_message = "输入无效，请重试。"


def input_user(existing_user: Optional[Dict], users: List[Dict]) -> Dict:
    base = normalize_user(existing_user or {})
    action_name = "编辑用户" if existing_user else "新增用户"

    existing_ids = {user_student_id(item) for item in users}
    current_id = user_student_id(base) if existing_user else None
    id_error = ""

    while True:
        header = f"{action_name}"
        if id_error:
            header = f"{header}\n\n{id_error}"

        student_id = prompt_int(users, "学号", current_id, header=header)
        if student_id == 0:
            id_error = "学号不能为空。"
            continue
        if student_id != current_id and student_id in existing_ids:
            id_error = "该学号已存在，请输入其他学号。"
            continue
        break

    username = prompt_text(users, "姓名", str(base.get("username", "")), header=action_name)
    password = prompt_text(users, "密码", str(base.get("password", DEFAULT_PASSWORD)), header=action_name)
    is_encrypted = prompt_int(users, "密码是否已加密(0/1)", int(base.get("is_encrypted", 0)), header=action_name)
    enabled = prompt_bool(users, "是否启用", bool(base.get("enabled", True)), header=action_name)
    latitude = prompt_float(users, "纬度", float(base.get("latitude", DEFAULT_LATITUDE)), header=action_name)
    longitude = prompt_float(users, "经度", float(base.get("longitude", DEFAULT_LONGITUDE)), header=action_name)
    email = prompt_text(users, "邮箱", str(base.get("email", "")), header=action_name)

    return {
        "student_id": student_id,
        "username": username,
        "password": password,
        "is_encrypted": is_encrypted,
        "enabled": enabled,
        "latitude": latitude,
        "longitude": longitude,
        "email": email,
    }


def persist_users(config: Dict, users: List[Dict]) -> str:
    config["users"] = users
    try:
        save_config(CONFIG_PATH, config)
    except Exception as exc:
        return f"保存失败: {exc}"
    return "保存成功。"


def toggle_user_enabled(users: List[Dict]) -> Optional[str]:
    index = choose_user_index(users, "切换状态")
    if index is None:
        return "已取消切换。"

    user = normalize_user(users[index])
    user["enabled"] = not bool(user.get("enabled", True))
    users[index] = user
    return f"已切换用户 {user_student_id(user)} 状态为: {'启用' if user['enabled'] else '禁用'}"


def main() -> int:
    try:
        config = load_config(CONFIG_PATH)
    except Exception as exc:
        print(f"读取配置失败: {exc}")
        return 1

    users = [normalize_user(item) for item in config.get("users", [])]
    message = ""

    while True:
        menu_header = (
            "可用操作\n"
            "[1] 新增用户\n"
            "[2] 编辑用户\n"
            "[3] 切换启用/禁用\n"
            "[4] 删除用户\n"
            "[0] 仅退出"
        )
        if message:
            menu_header = f"{message}\n\n{menu_header}"

        choice = prompt_text(users, "请选择操作(1/2/3/4/0)", header=menu_header)
        message = ""

        if choice == "1":
            new_user = input_user(None, users)
            users.append(new_user)
            message = "已新增用户。 " + persist_users(config, users)
        elif choice == "2":
            index = choose_user_index(users, "编辑")
            if index is not None:
                users[index] = input_user(users[index], users)
                message = "已更新用户。 " + persist_users(config, users)
            else:
                message = "已取消编辑。"
        elif choice == "3":
            toggle_message = toggle_user_enabled(users)
            if toggle_message:
                message = toggle_message
            if "已切换用户" in message:
                message = message + " " + persist_users(config, users)
        elif choice == "4":
            index = choose_user_index(users, "删除")
            if index is not None:
                user = users[index]
                confirm = prompt_bool(users, f"确认删除学号 {user_student_id(user)}", False, header="删除用户")
                if confirm:
                    del users[index]
                    message = "已删除用户。 " + persist_users(config, users)
                else:
                    message = "已取消删除。"
            else:
                message = "已取消删除。"
        elif choice == "0":
            render_prompt(users, "已退出。")
            return 0
        else:
            message = "无效选项，请输入 1/2/3/4/0。"


if __name__ == "__main__":
    sys.exit(main())






