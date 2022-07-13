from bs4 import BeautifulSoup
from config import email_address, password, imap_server, smtp_server
from envelope import Envelope
from flask import Flask, render_template, send_file, request
from flask_httpauth import HTTPBasicAuth
from imap_tools import A, U, MailBox
import os
import requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
auth = HTTPBasicAuth()

page_size = 20

users = {email_address: generate_password_hash(password)}

@auth.verify_password
def verify_password(email, pwd):
    if email in users and check_password_hash(users[email], pwd):
        return email

@app.route("/")
@auth.login_required
def inbox():
    return folder("INBOX", 1)

@app.route("/folder/<folder>/page/<page>")
@auth.login_required
def folder(folder, page):
    page = int(page)
    with MailBox(imap_server).login(email_address, password) as mailbox:
        folders = [folder.name for folder in mailbox.folder.list()]

        mailbox.folder.set(folder)
        message_uids = mailbox.uids()

        page_count = (len(message_uids) / page_size) if (len(message_uids) % page_size) == 0 else (int(len(message_uids) / page_size) + 1)
        page = max(page, 1)
        page = min(page, page_count)

        start_index = 0 if (len(message_uids) < (page * page_size)) else (len(message_uids) - (page * page_size))
        end_index = len(message_uids) - ((page - 1) * page_size) - 1

        messages = mailbox.fetch(A(uid=U(message_uids[start_index], message_uids[end_index])), reverse=True) if len(message_uids) > 0 else []
        return render_template("folder.html", folders=folders, current_folder=folder, current_page=page, messages=messages)

@app.route("/folder/<folder>/message/<message_id>")
@auth.login_required
def message(folder, message_id):
    with MailBox(imap_server).login(email_address, password) as mailbox:
        folders = [folder.name for folder in mailbox.folder.list()]

        mailbox.folder.set(folder)
        message = [m for m in mailbox.fetch(A(uid=message_id))][0]
        recipients = message.to + message.cc + message.bcc
        recipients = ", ".join(recipients)
        soup = BeautifulSoup(message.html, 'html.parser')
        return render_template("message.html", folders=folders, current_folder=folder, message=message, recipients=recipients, body=soup.get_text())

@app.route("/folder/<folder>/message/<message_id>/attachment/<filename>")
@auth.login_required
def attachment(folder, message_id, filename):
    with MailBox(imap_server).login(email_address, password) as mailbox:
        mailbox.folder.set(folder)
        message = [m for m in mailbox.fetch(A(uid=message_id))][0]
        for attachment in message.attachments:
            if filename == attachment.filename:
                with open(filename, "wb") as f:
                    f.write(attachment.payload)
                response = send_file(filename)
                os.remove(filename)
                return response

@app.route("/compose")
@auth.login_required
def compose():
    with MailBox(imap_server).login(email_address, password) as mailbox:
        folders = [folder.name for folder in mailbox.folder.list()]
        return render_template("compose.html", folders=folders)

@app.route("/compose/<folder>/<message_id>")
@auth.login_required
def reply_all(folder, message_id):
    with MailBox(imap_server).login(email_address, password) as mailbox:
        folders = [folder.name for folder in mailbox.folder.list()]

        mailbox.folder.set(folder)
        message = [m for m in mailbox.fetch(A(uid=message_id))][0]
        subject = message.subject if message.subject.lower().startswith("re:") else "RE: " + message.subject
        recipients = (message.from_, ) + message.to + message.cc + message.bcc
        recipients = list(filter(lambda email: email != email_address, recipients))
        recipients = ", ".join(recipients)
        soup = BeautifulSoup(message.html, 'html.parser')
        return render_template("compose.html", folders=folders, message=message, subject=subject, recipients=recipients, body=soup.get_text())

@app.route("/send", methods=["POST"])
def send():
    if request.method == "POST":
        data = request.form
        recipients = data["recipients"]
        subject = data["subject"]
        body = data["body"]
        attachments = request.files["attachments"]
        message = Envelope(body).subject(subject)
        for attachment in attachments:
            attachment.save(attachment.filename)


if __name__ == "__main__":
    app.run(debug=True)
