# Node Deploy Checklist Through Hive Shell

## Preflight

- Resolve farm and worker.
- Confirm worker is online.
- Confirm target disk has enough space:

```bash
df -h /
df -h /opt || true
free -h
uname -a
```

- Confirm whether the node can run beside mining workload.
- Ask for confirmation before package installs, firewall changes, or service creation.

## Durable setup

Use:

```text
/opt/<project>
/var/log/hermess/<project>.log
/run/hermess/<project>.pid
/opt/<project>/hermess-state.json
```

Run long work in:

```bash
tmux new -d -s hermess-<project> '<command>'
```

or as:

```bash
systemctl enable --now <project>
```

## Status checks

```bash
tmux ls
pgrep -af '<project>'
systemctl status <project> --no-pager
journalctl -u <project> -n 120 --no-pager
tail -n 120 /var/log/hermess/<project>.log
cat /opt/<project>/hermess-state.json
```

## Recovery

If Hive Shell expired:

1. Start `hssh`.
2. Poll messages with payload.
3. Reconnect.
4. Run status checks.
5. Continue from state file/logs.

