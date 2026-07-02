# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Entry point: python -m hound <command>"""

from __future__ import annotations

import sys


def main() -> None:
    from .cli.parser import build_parser
    from .cli.cmd_start import do_start
    from .cli.cmd_status import do_status
    from .cli.cmd_alerts import do_alerts
    from .cli.cmd_report import do_report
    from .cli.cmd_gate import do_gate
    from .config.loader import load_config
    from .memory.db import Database
    from .memory.alert_store import AlertStore

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    cmd = args.command

    if cmd == "start":
        do_start(config_path=args.config, daemon=args.daemon)
    elif cmd == "stop":
        _do_stop(args.config)
    elif cmd == "status":
        do_status(config_path=args.config)
    elif cmd == "alerts":
        do_alerts(config_path=args.config, show_all=args.all)
    elif cmd == "ack":
        _do_ack(args.config, args.alert_id)
    elif cmd == "report":
        do_report(config_path=args.config)
    elif cmd == "baseline":
        _do_baseline(args.config)
    elif cmd == "gate":
        do_gate(config_path=args.config, min_quality=args.min_quality, last_turns=args.last_turns)
    else:
        parser.print_help()
        sys.exit(1)


def _do_stop(config_path) -> None:
    from .config.loader import load_config
    import os, signal

    cfg = load_config(config_path)
    pid_file = cfg.output_dir / "hound.pid"
    if not pid_file.exists():
        print("hound: no PID file found; is the daemon running?")
        return
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        print(f"hound: sent SIGTERM to PID {pid}")
    except ProcessLookupError:
        print(f"hound: process {pid} not found; cleaning up PID file")
        pid_file.unlink(missing_ok=True)


def _do_ack(config_path, alert_id: int) -> None:
    from .config.loader import load_config
    from .memory.db import Database
    from .memory.alert_store import AlertStore

    cfg = load_config(config_path)
    db = Database(cfg.state_db_path)
    conn = db.connect()
    store = AlertStore(conn)
    store.record_acked(alert_id)
    print(f"hound: alert {alert_id} acknowledged")


def _do_baseline(config_path) -> None:
    from .cli.cmd_report import do_report
    print("hound: running full analysis to recompute baselines…")
    do_report(config_path)
    print("hound: baselines updated")


if __name__ == "__main__":
    main()
