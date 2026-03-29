import logging
import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from typing import Dict, List, Optional

from .constants import DATETIME_FORMAT
from .models import UserConfig


class Mailer:
    def __init__(self, email_config: dict):
        self.email_config = email_config if isinstance(email_config, dict) else {}

    @staticmethod
    def build_mail_subject(result: dict) -> str:
        return "✅ 签到成功通知" if result.get("success") else "❌ 签到失败通知"

    @staticmethod
    def build_result_detail_text(result: dict) -> str:
        failure_logs = result.get("failure_logs", [])
        if failure_logs:
            return "\n".join(str(item) for item in failure_logs)

        errors = result.get("errors", [])
        if errors:
            return "\n".join(str(item) for item in errors)

        return "无异常日志"

    @staticmethod
    def format_enabled_status(enabled: bool) -> str:
        return "🟢 已开启" if enabled else "⚪ 已关闭"

    @staticmethod
    def format_sign_status(success: bool) -> str:
        return "✅ 成功" if success else "❌ 失败"

    @staticmethod
    def format_display_time(time_value: Optional[object]) -> str:
        if time_value is None:
            return "-"
        if isinstance(time_value, datetime):
            return time_value.strftime(DATETIME_FORMAT)
        text = str(time_value).strip()
        return text or "-"

    @staticmethod
    def build_result_card_html(user: UserConfig, result: dict, role_label: str) -> str:
        display_name = escape(user.username or "") or str(user.student_Id)
        status_text = Mailer.format_sign_status(bool(result.get("success")))

        detail_section = ""
        if not result.get("success"):
            details = escape(Mailer.build_result_detail_text(result))
            detail_section = f"<pre>{details}</pre>"

        return (
            "<section style='font-family: Arial, sans-serif; line-height: 1.6;'>"
            f"<h3 style='margin: 0 0 8px 0;'>{escape(role_label)}</h3>"
            f"<p style='margin: 0;'>姓名: {display_name}</p>"
            f"<p style='margin: 0;'>学号: {user.student_Id}</p>"
            f"<p style='margin: 0;'>时间: {escape(datetime.now().strftime(DATETIME_FORMAT))}</p>"
            f"<p style='margin: 8px 0 0 0;'>签到结果: {status_text}</p>"
            f"{detail_section}"
            "</section>"
        )

    @staticmethod
    def build_summary_table_block_html(
        all_users: List[UserConfig],
        results: Dict[int, dict],
        next_day_eta_map: Optional[Dict[int, datetime]] = None,
    ) -> str:
        rows = []
        eta_map = next_day_eta_map or {}

        for user in all_users:
            user_result = results.get(user.student_Id)
            enabled_status = Mailer.format_enabled_status(user.enabled)
            sign_status = Mailer.format_sign_status(bool(user_result and user_result.get("success")))
            sign_time = Mailer.format_display_time(user_result.get("sign_time") if user_result else None)
            next_day_eta = Mailer.format_display_time(eta_map.get(user.student_Id))

            rows.append(
                "<tr>"
                f"<td>{escape(user.username or '')}</td>"
                f"<td>{user.student_Id}</td>"
                f"<td>{escape(user.email)}</td>"
                f"<td>{enabled_status}</td>"
                f"<td>{sign_status}</td>"
                f"<td>{escape(sign_time)}</td>"
                f"<td>{escape(next_day_eta)}</td>"
                "</tr>"
            )

        return (
            f"<p>汇总时间: {escape(datetime.now().strftime(DATETIME_FORMAT))}</p>"
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse;'>"
            "<thead><tr><th>姓名</th><th>学号</th><th>邮箱</th><th>签到开启</th><th>签到结果</th><th>签到时间</th><th>次日预计签到时间</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

    @staticmethod
    def build_summary_table_html(
        all_users: List[UserConfig],
        results: Dict[int, dict],
        next_day_eta_map: Optional[Dict[int, datetime]] = None,
    ) -> str:
        return "<html><body>" + Mailer.build_summary_table_block_html(all_users, results, next_day_eta_map) + "</body></html>"

    def send_mail(self, to_email: str, subject: str, body: str, subtype: str = "plain") -> bool:
        if not self.email_config.get("enabled", False):
            return False
        if not to_email:
            logging.warning("skip email: receiver email is empty")
            return False

        required = ["smtp_server", "smtp_port", "sender_email", "sender_password"]
        missing = [key for key in required if not self.email_config.get(key)]
        if missing:
            logging.error("email config missing required keys: %s", missing)
            return False

        message = MIMEText(body, subtype, "utf-8")
        message["Subject"] = Header(subject, "utf-8")

        sender_name = str(self.email_config.get("sender_name", "AHUT Auto Sign-In"))
        sender_email = str(self.email_config["sender_email"])
        sender_password = str(self.email_config["sender_password"])

        message["From"] = formataddr((str(Header(sender_name, "utf-8")), sender_email))
        message["To"] = to_email

        smtp_server = str(self.email_config["smtp_server"])
        smtp_port = int(self.email_config["smtp_port"])

        try:
            if self.email_config.get("use_ssl", True):
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
                if self.email_config.get("use_tls", True):
                    server.starttls(context=ssl.create_default_context())

            with server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], message.as_string())

            logging.info("email sent to %s", to_email)
            return True
        except Exception as exc:
            logging.error("failed to send email to %s: %s", to_email, exc)
            return False

    def send_email_for_user(self, user: UserConfig, result: dict) -> None:
        html_body = "<html><body>" + self.build_result_card_html(user, result, "👤 签到结果") + "</body></html>"
        self.send_mail(
            to_email=user.email,
            subject=self.build_mail_subject(result),
            body=html_body,
            subtype="html",
        )

    def send_summary_email_to_first_user(
        self,
        all_users: List[UserConfig],
        results: Dict[int, dict],
        next_day_eta_map: Optional[Dict[int, datetime]] = None,
    ) -> None:
        if not all_users:
            return

        first_user = all_users[0]
        summary_html = self.build_summary_table_html(all_users, results, next_day_eta_map)
        self.send_mail(
            to_email=first_user.email,
            subject="📋 签到汇总",
            body=summary_html,
            subtype="html",
        )

    def send_combined_email_to_admin_when_signed(
        self,
        admin_user: UserConfig,
        admin_result: dict,
        all_users: List[UserConfig],
        results: Dict[int, dict],
        next_day_eta_map: Optional[Dict[int, datetime]] = None,
    ) -> None:
        html_body = (
            "<html><body>"
            + self.build_result_card_html(admin_user, admin_result, "🛡️ 管理员签到结果")
            + "<hr/>"
            + "<h3>📊 全员签到汇总</h3>"
            + self.build_summary_table_block_html(all_users, results, next_day_eta_map)
            + "</body></html>"
        )

        self.send_mail(
            to_email=admin_user.email,
            subject=self.build_mail_subject(admin_result),
            body=html_body,
            subtype="html",
        )
