#!/usr/bin/env -S 'PYTHONUNBUFFERED=1 PYTHONIOENCODING="utf-8"' python3
import sys
import sqlite3
import datetime
import json
import email
from email.policy import default as email_policy
import syslog
from pathlib import Path

# 1. In /etc/aliases:
# sic: "| sudo -u user /path/to/sic/tools/mailing_list_rcv.py"
# 2. Run newaliases
# 3: chmod u+x /path/to/sic/tools/mailing_list_rcv.py
# 4. Run visudo and insert:
# nobody ALL=(user:user) NOPASSWD: /path/to/sic/tools/mailing_list_rcv.py

# Local testing using msmtp:
# msmtp --host=localhost --read-envelope-from -t < mail.eml
# or
# sendmail -t < mail.eml

DOTTED_PATH = "sic.mail.post_receive_job"


def normalize_email(addr):
    """
    Normalize the email address by lowercasing the domain part of it.
    """
    addr = addr or ""
    try:
        email_name, domain_part = addr.strip().rsplit("@", 1)
    except ValueError:
        pass
    else:
        addr = email_name + "@" + domain_part.lower()
    return addr


if __name__ == "__main__":
    syslog.syslog("Received mail, reading from STDIN...")
    data = None
    try:
        base_dir = Path(__file__).resolve().parent.parent
        data = sys.stdin.read()
        syslog.syslog(f"Got {len(data)} bytes.")
        msg = email.message_from_string(data, policy=email_policy)
        if "From" not in msg:
            syslog.syslog("No From: header, discarding.")
            syslog.syslog(data)
            sys.exit(0)
        from_ = msg["from"].addresses[0].addr_spec
        with sqlite3.connect(base_dir / "sic.db") as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM sic_user WHERE email = ?", (normalize_email(from_),)
            )
            if not cur.fetchone():
                syslog.syslog(f"User with email {from_} not found, discarding.")
                syslog.syslog(data)
                sys.exit(0)
            now = datetime.datetime.now()
            cur.execute(
                "INSERT OR IGNORE INTO sic_jobkind(dotted_path, created, last_modified) VALUES (?, ?, ?)",
                (DOTTED_PATH, now, now),
            )
            cur.execute(
                "SELECT id FROM sic_jobkind WHERE dotted_path = ?", (DOTTED_PATH,)
            )
            kind_id = cur.fetchone()[0]
            cur.execute(
                "INSERT OR ABORT INTO sic_job(created, active, periodic, failed, data, kind_id) VALUES (?, ?, ?, ?, ?, ?)",
                (now, True, False, False, json.dumps(data), kind_id),
            )
        syslog.syslog("Queued mail successfuly.")
    except Exception as exc:
        syslog.syslog(syslog.LOG_ERR, str(exc))
        if isinstance(data, str):
            syslog.syslog(syslog.LOG_ERR, data)
        else:
            syslog.syslog(syslog.LOG_ERR, "No data.")
