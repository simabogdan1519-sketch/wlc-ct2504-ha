# Contributing

Thank you for considering a contribution! This is a small focused project, so contributions are welcome but please keep them scoped.

## What's welcome

- Bug fixes with a clear reproduction case
- New SNMP sensors that are relevant to the CT2504 (open an issue first)
- Improved error handling or reliability fixes
- Translation improvements or new languages

## What's out of scope

- Support for non-Cisco controllers
- SNMP v3 support (until pysnmp integration is stable in HA)
- UI redesign of the Lovelace card (subjective)

## How to contribute

1. Fork the repo
2. Create a branch: `git checkout -b fix/ap-index-stability`
3. Make your changes
4. Test against a real CT2504 or a mock SNMP agent (see below)
5. Open a pull request with a clear description

## Testing locally

Copy the integration to your HA config:

```bash
cp -r custom_components/wlc_ct2504 /path/to/ha/config/custom_components/
```

Enable debug logging in HA `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.wlc_ct2504: debug
```

Restart HA and check **Settings → System → Logs**.

## Mock SNMP agent (no physical WLC needed)

You can use `snmpsim` to replay a real WLC walk for development:

```bash
pip install snmpsim
# Record a walk from your real WLC:
snmprec.py --agent-udpv4-endpoint=<WLC_IP>:161 --community=public \
  --output-file=wlc.snmprec
# Replay it locally:
snmpsimd.py --data-dir=. --agent-udpv4-endpoint=127.0.0.1:1161
```

Then configure the integration with `host: 127.0.0.1` and `port: 1161`.

## Code style

- Follow existing patterns in the codebase
- Use type hints everywhere
- Keep OIDs in `const.py`, not inline
- All user-facing strings go in `translations/en.json` and `translations/ro.json`
