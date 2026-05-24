# Setup — HTTPS for the player + admin web UIs

The two web UIs ship with plain HTTP listeners (player on `:8090`,
admin on `:8080`). That's fine on the Pi itself, but browsers gate
`navigator.mediaDevices.getUserMedia` (i.e. the voice page's
microphone) behind a "secure context" — meaning either HTTPS or
`localhost`. The moment you open the player web-UI from a phone /
laptop over plain LAN HTTP (`http://192.168.178.71:8090`), voice mode
is dead with a cryptic `TypeError: Cannot read properties of
undefined (reading 'getUserMedia')`.

This page sets up [Caddy](https://caddyserver.com) as a TLS reverse
proxy and a local certificate authority via
[mkcert](https://github.com/FiloSottile/mkcert). After the one-time
setup:

* `https://story.local/` → player web-UI (text, voice, `/create`)
* `https://story.local:8443/` → admin web-UI
* `http://story.local/` → 301 redirect to HTTPS

Each remote device (phone, PC) only needs to install **one** root
certificate (`rootCA.pem`) once — after that the UIs load with a
green lock and voice mode works everywhere.

## On the Pi: one-shot setup script

```bash
bash scripts/install_https.sh
```

That handles everything:

1. `apt install caddy libnss3-tools` (Debian 13 trixie has Caddy 2.6).
2. Downloads the `mkcert` binary into `/usr/local/bin/`.
3. Runs `mkcert -install` so the system trust store knows the local CA.
4. Generates a server cert covering `story.local`, `storyteller.local`,
   `localhost`, `127.0.0.1` and the Pi's detected LAN IPv4.
5. Writes `/etc/caddy/Caddyfile` with three listeners
   (`:80 redirect`, `:443 → 8090`, `:8443 → 8080`).
6. Enables + restarts the `caddy` systemd unit.

Files end up at:

| Path | Purpose |
|---|---|
| `/etc/storyteller/mkcert/rootCA.pem` | local CA (copy this onto remote devices) |
| `/etc/storyteller/mkcert/rootCA-key.pem` | local CA private key — **never share** |
| `/etc/storyteller/mkcert/storyteller-cert.pem` | server cert |
| `/etc/storyteller/mkcert/storyteller-key.pem` | server private key (root:caddy 0640) |
| `/etc/caddy/Caddyfile` | reverse-proxy config |
| `/usr/local/bin/mkcert` | mkcert binary |

The script is idempotent: re-running it re-issues the server cert
(useful when the Pi's IP changes) but **does not** rotate the root
CA, so devices that already trust it stay trusted.

## On each remote device: install the root CA once

Copy `/etc/storyteller/mkcert/rootCA.pem` from the Pi to the device
(e.g. via `scp`, AirDrop, mail to yourself), then install it into the
system trust store.

### macOS

```bash
# from a terminal on the Mac:
scp pi@story.local:/etc/storyteller/mkcert/rootCA.pem ~/Downloads/storyteller-rootCA.pem
sudo security add-trusted-cert -d \
    -r trustRoot -k /Library/Keychains/System.keychain \
    ~/Downloads/storyteller-rootCA.pem
```

Or via Keychain Access: drag `rootCA.pem` into the *System* keychain,
double-click it, expand *Trust*, set *When using this certificate* to
*Always Trust*.

### Linux (Debian / Ubuntu)

```bash
sudo cp rootCA.pem /usr/local/share/ca-certificates/storyteller-rootCA.crt
sudo update-ca-certificates
```

Firefox / Chromium use their own NSS DB:

```bash
sudo apt install libnss3-tools
certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n storyteller -i rootCA.pem
```

### Windows

Double-click the `rootCA.pem` file → *Install Certificate* → *Local
Machine* → *Place all certificates in the following store* →
*Trusted Root Certification Authorities* → Finish.

### iOS / iPadOS

1. Email or AirDrop the `rootCA.pem` to the device.
2. Open it → iOS asks to install a profile → *Allow*.
3. *Settings → General → VPN & Device Management → Storyteller* →
   *Install*.
4. **Important second step**: *Settings → General → About → Certificate
   Trust Settings* → toggle *Storyteller* on.

### Android

*Settings → Security → More security settings → Encryption &
credentials → Install a certificate → CA certificate*. Pick the
`rootCA.pem`. Android calls out that the network may be monitored;
that's expected for a private CA.

## Hostname resolution: `story.local`

The Pi's hostname is `story`, advertised over mDNS / Bonjour, so most
modern desktops and Android resolve `story.local` to the Pi
automatically. iOS / macOS use Bonjour natively. If a device can't
resolve `story.local`, fall back to the LAN IP — the cert covers it
too: `https://192.168.178.71/` (replace with the IP shown by
`hostname -I` on the Pi).

## Updating the cert when the LAN IP changes

```bash
bash scripts/install_https.sh   # re-runs; picks up the new IP
```

Browsers cache the cert — close + reopen the tab.

## Bypassing without setup

Voice mode also works from these contexts without any HTTPS:

* On the Pi itself: `http://localhost:8090/voice`
* Chrome's per-origin override: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
  → add `http://192.168.178.71:8090` → relaunch. Per device, per
  browser — useful for one-off tests but not for permanent setups.

## What stays on plain HTTP

The two FastAPI processes keep binding to `0.0.0.0:8080` /
`0.0.0.0:8090` as before. That's intentional — the HTTPS proxy is
strictly additive so existing tooling (curl smoke tests, the admin
restart workflow, ssh tunnelling) keeps working. If you want to
**force** HTTPS only, tighten the systemd units to bind those
ports to `127.0.0.1` instead of `0.0.0.0`; Caddy will still
reach them on localhost.
