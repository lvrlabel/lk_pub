"""Фоновые задачи биллинга (раз в сутки при запросах к приложению)."""

import os
import time

from flask import current_app

_last_run_ts = 0
_INTERVAL_SEC = 24 * 3600


def run_billing_tasks_if_due():
    """Не чаще раза в 24 часа: просрочки и напоминания о подписке."""
    global _last_run_ts
    now = time.time()
    if now - _last_run_ts < _INTERVAL_SEC:
        return

    try:
        instance = current_app.instance_path
        os.makedirs(instance, exist_ok=True)
        stamp_path = os.path.join(instance, '.billing_tasks_last_run')
        if os.path.isfile(stamp_path):
            try:
                with open(stamp_path, 'r', encoding='utf-8') as f:
                    last = float(f.read().strip() or '0')
                if now - last < _INTERVAL_SEC:
                    _last_run_ts = now
                    return
            except (ValueError, OSError):
                pass

        from app.services.subscription_service import (
            process_overdue_invoices,
            process_subscription_reminders,
        )

        process_overdue_invoices()
        process_subscription_reminders()

        with open(stamp_path, 'w', encoding='utf-8') as f:
            f.write(str(now))
        _last_run_ts = now
    except Exception as e:
        current_app.logger.warning('billing_scheduler: %s', e)
