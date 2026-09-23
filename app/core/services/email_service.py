"""Serviço de envio de emails via SMTP"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from ..config import settings

# Template base para emails
EMAIL_BASE_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        line-height: 1.6;
        color: #374151;
        margin: 0;
        padding: 0;
        background-color: #f3f4f6;
        -webkit-font-smoothing: antialiased;
    }
    .wrapper {
        background-color: #f3f4f6;
        padding: 40px 20px;
    }
    .container {
        max-width: 560px;
        margin: 0 auto;
    }
    .card {
        background: white;
        border-radius: 20px;
        padding: 48px 40px;
        box-shadow: 0 4px 24px rgba(30, 58, 95, 0.08);
    }
    .header {
        text-align: center;
        margin-bottom: 32px;
        padding-bottom: 32px;
        border-bottom: 1px solid #e5e7eb;
    }
    .logo-img {
        height: 48px;
        margin-bottom: 8px;
    }
    .slogan {
        font-size: 13px;
        color: #9ca3af;
        margin: 0;
        letter-spacing: 0.5px;
    }
    h2 {
        font-size: 22px;
        font-weight: 600;
        color: #111827;
        margin: 0 0 20px;
    }
    p {
        color: #6b7280;
        margin: 0 0 16px;
        font-size: 15px;
    }
    .highlight {
        color: #1E3A5F;
        font-weight: 600;
    }
    .button-container {
        text-align: center;
        margin: 32px 0;
    }
    .button {
        display: inline-block;
        background: linear-gradient(135deg, #1E3A5F 0%, #2d4a6f 100%);
        color: white !important;
        text-decoration: none;
        padding: 16px 40px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 15px;
        box-shadow: 0 4px 14px rgba(30, 58, 95, 0.3);
        transition: all 0.2s;
    }
    .features {
        background: #f8fafc;
        border-radius: 12px;
        padding: 20px 24px;
        margin: 24px 0;
    }
    .features ul {
        margin: 0;
        padding: 0 0 0 20px;
        color: #6b7280;
    }
    .features li {
        margin: 8px 0;
        font-size: 14px;
    }
    .features li::marker {
        color: #1E3A5F;
    }
    .warning {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: #d97706;
        background: #fef3c7;
        padding: 10px 16px;
        border-radius: 8px;
        margin-top: 8px;
    }
    .info-box {
        font-size: 13px;
        color: #9ca3af;
        margin-top: 24px;
        padding: 16px;
        background: #f9fafb;
        border-radius: 10px;
        border: 1px solid #e5e7eb;
    }
    .footer {
        text-align: center;
        margin-top: 32px;
        padding-top: 24px;
        border-top: 1px solid #e5e7eb;
    }
    .footer-logo-img {
        height: 32px;
        margin-bottom: 4px;
    }
    .footer-slogan {
        font-size: 12px;
        color: #9ca3af;
        margin: 0;
        letter-spacing: 0.3px;
    }
    .footer-links {
        margin-top: 16px;
        font-size: 12px;
        color: #9ca3af;
    }
    .footer-links a {
        color: #6b7280;
        text-decoration: none;
    }
</style>
"""


class EmailService:
    """Serviço para envio de emails"""

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.use_ssl = settings.smtp_use_ssl
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_name = settings.smtp_from_name
        self.from_email = settings.smtp_from_email or settings.smtp_user

    def _get_connection(self):
        """Cria conexão SMTP"""
        if self.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(self.host, self.port, context=context)
        else:
            server = smtplib.SMTP(self.host, self.port)
            server.starttls()

        if self.user and self.password:
            server.login(self.user, self.password)

        return server

    def send_email(
        self, to_email: str, subject: str, html_content: str, text_content: str = None
    ) -> bool:
        """Envia email HTML com cabeçalhos para melhor entregabilidade"""
        if not self.user or not self.password:
            print("SMTP não configurado - email não enviado")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            # Cabeçalhos para melhorar entregabilidade
            msg["Message-ID"] = make_msgid(domain="biveto.com")
            msg["Date"] = formatdate(localtime=True)
            msg["Reply-To"] = self.from_email
            msg["X-Mailer"] = "Koin Mail Service"

            # Versão texto puro (importante para não ir para spam)
            if text_content:
                text_part = MIMEText(text_content, "plain", "utf-8")
                msg.attach(text_part)

            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(html_part)

            with self._get_connection() as server:
                server.sendmail(self.from_email, to_email, msg.as_string())

            return True
        except Exception as e:
            print(f"Erro ao enviar email: {e}")
            return False

    def send_invitation(self, to_email: str, invite_url: str, inviter_name: str) -> bool:
        """Envia email de convite"""
        subject = "Você foi convidado para o Koin"

        # Versão texto puro (importante para entregabilidade)
        text_content = f"""
Você foi convidado para o Koin!

{inviter_name} convidou você para acessar o Koin — seu assistente inteligente de finanças pessoais.

Com o Koin você pode:
- Importar faturas automaticamente com IA
- Controlar gastos e criar orçamentos
- Definir e acompanhar metas financeiras
- Receber insights personalizados

Clique no link abaixo para criar sua conta:
{invite_url}

Este convite expira em 48 horas.

--
Koin — finanças claras. decisões firmes.
https://biveto.com
"""

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {EMAIL_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <div class="card">
                <div class="header">
                    <img src="https://biveto.com/logo.png" alt="Koin" class="logo-img">
                    <p class="slogan">finanças claras. decisões firmes.</p>
                </div>

                <h2>Você foi convidado!</h2>

                <p>
                    <span class="highlight">{inviter_name}</span> convidou você para acessar o
                    <span class="highlight">Koin</span> — seu assistente inteligente de finanças pessoais.
                </p>

                <div class="features">
                    <p style="margin: 0 0 12px; font-weight: 500; color: #374151;">Com o Koin você pode:</p>
                    <ul>
                        <li>Importar faturas automaticamente com IA</li>
                        <li>Controlar gastos e criar orçamentos</li>
                        <li>Definir e acompanhar metas financeiras</li>
                        <li>Receber insights personalizados</li>
                    </ul>
                </div>

                <div class="button-container">
                    <a href="{invite_url}" class="button">Criar minha conta</a>
                </div>

                <div style="text-align: center;">
                    <span class="warning">
                        Este convite expira em 48 horas
                    </span>
                </div>

                <div class="footer">
                    <img src="https://biveto.com/logo.png" alt="Koin" class="footer-logo-img">
                    <p class="footer-slogan">finanças claras. decisões firmes.</p>
                    <p class="footer-links">
                        © 2025 Koin · <a href="https://biveto.com">biveto.com</a>
                    </p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
        return self.send_email(to_email, subject, html_content, text_content)

    def send_password_reset(self, to_email: str, reset_url: str, user_name: str) -> bool:
        """Envia email de redefinição de senha"""
        subject = "Redefinir sua senha - Koin"

        # Versão texto puro
        text_content = f"""
Redefinição de senha

Olá {user_name},

Recebemos uma solicitação para redefinir a senha da sua conta no Koin.
Clique no link abaixo para criar uma nova senha:

{reset_url}

Este link expira em 1 hora.

Não solicitou essa alteração?
Se você não pediu para redefinir sua senha, ignore este email.
Sua senha permanecerá a mesma e sua conta está segura.

--
Koin — finanças claras. decisões firmes.
https://biveto.com
"""

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {EMAIL_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <div class="card">
                <div class="header">
                    <img src="https://biveto.com/logo.png" alt="Koin" class="logo-img">
                    <p class="slogan">finanças claras. decisões firmes.</p>
                </div>

                <h2>Redefinição de senha</h2>

                <p>
                    Olá <span class="highlight">{user_name}</span>,
                </p>

                <p>
                    Recebemos uma solicitação para redefinir a senha da sua conta no Koin.
                    Clique no botão abaixo para criar uma nova senha:
                </p>

                <div class="button-container">
                    <a href="{reset_url}" class="button">Redefinir minha senha</a>
                </div>

                <div style="text-align: center;">
                    <span class="warning">
                        Este link expira em 1 hora
                    </span>
                </div>

                <div class="info-box">
                    <strong>Não solicitou essa alteração?</strong><br>
                    Se você não pediu para redefinir sua senha, ignore este email.
                    Sua senha permanecerá a mesma e sua conta está segura.
                </div>

                <div class="footer">
                    <img src="https://biveto.com/logo.png" alt="Koin" class="footer-logo-img">
                    <p class="footer-slogan">finanças claras. decisões firmes.</p>
                    <p class="footer-links">
                        © 2025 Koin · <a href="https://biveto.com">biveto.com</a>
                    </p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
        return self.send_email(to_email, subject, html_content, text_content)

    def send_password_changed_notification(self, to_email: str, user_name: str) -> bool:
        """Envia notificação de que a senha foi alterada"""
        subject = "Sua senha foi alterada - Koin"

        # Versão texto puro
        text_content = f"""
Senha alterada com sucesso

Olá {user_name},

Sua senha do Koin foi alterada com sucesso.

Se você fez essa alteração, pode ignorar este email.

Se você NÃO alterou sua senha, sua conta pode estar comprometida.
Entre em contato conosco imediatamente respondendo este email.

--
Koin — finanças claras. decisões firmes.
https://biveto.com
"""

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {EMAIL_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <div class="card">
                <div class="header">
                    <img src="https://biveto.com/logo.png" alt="Koin" class="logo-img">
                    <p class="slogan">finanças claras. decisões firmes.</p>
                </div>

                <h2>Senha alterada com sucesso</h2>

                <p>
                    Olá <span class="highlight">{user_name}</span>,
                </p>

                <p>
                    Sua senha do Koin foi alterada com sucesso.
                </p>

                <p>
                    Se você fez essa alteração, pode ignorar este email.
                </p>

                <div class="info-box" style="background: #fef2f2; border-color: #fecaca;">
                    <strong style="color: #dc2626;">Não reconhece essa alteração?</strong><br>
                    Se você NÃO alterou sua senha, sua conta pode estar comprometida.
                    Entre em contato conosco imediatamente respondendo este email.
                </div>

                <div class="footer">
                    <img src="https://biveto.com/logo.png" alt="Koin" class="footer-logo-img">
                    <p class="footer-slogan">finanças claras. decisões firmes.</p>
                    <p class="footer-links">
                        © 2025 Koin · <a href="https://biveto.com">biveto.com</a>
                    </p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
        return self.send_email(to_email, subject, html_content, text_content)


email_service = EmailService()
