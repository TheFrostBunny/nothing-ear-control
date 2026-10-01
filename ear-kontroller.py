#!/usr/bin/env python3
"""Nothing Ear (2) / Ear (2024)-kontroller for Windows og Linux (kun standardbiblioteket).

Protokoll: https://bharadwajraju.com/posts/nothing-ear-2-on-linux/
Pakkene er hentet fra artikkelen. CRC-en regnes ut på nytt
før sending.

Eksempler:
    python ear2.py                              # åpner vinduet (GUI)
    python ear2.py list                      # vis parede enheter
    python ear2.py --device AA:BB:CC:DD:EE:FF --save anc transparency
    python ear2.py anc high
    python ear2.py get-anc
    python ear2.py in-ear off
    python ear2.py latency on
    python ear2.py fit-test
    python ear2.py raw 55:60:01:...
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
RFCOMM_CHANNEL = 15
CONFIG = Path.home() / ".nothing-ear" / "config.json"
MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

PACKETS = {
    "anc": {
        "transparency": "5560010ff00300cb010700c5af",
        "off": "5560010ff00300cd010500c447",
        "high": "5560010ff00300cf010100e66f",
        "mid": "5560010ff00300d5010200e69f",
        "low": "5560010ff00300d7010300e70f",
        "adaptive": "5560010ff00300dd010400e53f",
    },
    "in-ear": {
        "off": "55600104f0030025010100b294",
        "on": "55600104f00300260101017310",
    },
    "latency": {
        "off": "55600140f00200280200a704",
        "on": "55600140f0020027010097f7",
    },
}
FIT_TEST = "55600114f001002a014316"
QUERY = "5560011ec001000c039819"

# Byte 9 i svaret på QUERY er ANC-modus (ifølge eksempelkoden)
ANC_BYTE = {1: "HIGH", 2: "MID", 3: "LOW", 4: "ADAPTIVE", 5: "OFF", 7: "TRANSPARENCY"}


# Konfigurasjon

def load_saved_address():
    try:
        return json.loads(CONFIG.read_text()).get("device_address")
    except (OSError, json.JSONDecodeError):
        return None


def save_address(addr):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"device_address": addr}, indent=2))
    print(f"Lagret adresse i {CONFIG}")


# Finn enheter (plattformspesifikt)

def list_devices():
    """Returnerer [(navn, mac)] for parede Bluetooth-enheter."""
    devices = []
    try:
        if IS_WINDOWS:
            ps = ("Get-PnpDevice -Class Bluetooth | "
                  "Select-Object FriendlyName,InstanceId | ConvertTo-Json")
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=15,
            ).stdout.strip()
            if out:
                data = json.loads(out)
                if isinstance(data, dict):  # ett treff gir objekt, ikke liste
                    data = [data]
                seen = set()
                for d in data:
                    m = re.search(r"DEV_([0-9A-Fa-f]{12})", d.get("InstanceId") or "")
                    if m and m.group(1) not in seen:
                        seen.add(m.group(1))
                        h = m.group(1).upper()
                        mac = ":".join(h[i:i + 2] for i in range(0, 12, 2))
                        devices.append((d.get("FriendlyName") or "?", mac))
        else:
            out = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            for line in out.splitlines():
                m = re.match(r"Device\s+(\S+)\s+(.*)", line.strip())
                if m and MAC_RE.match(m.group(1)):
                    devices.append((m.group(2), m.group(1).upper()))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return devices


def resolve_address(arg):
    addr = arg or os.environ.get("NOTHING_EAR_DEVICE") or load_saved_address()
    if not addr:
        # Prøv å finne enheten automatisk
        found = [d for d in list_devices()
                 if "nothing" in d[0].lower() or "ear" in d[0].lower()]
        if len(found) == 1:
            addr = found[0][1]
            print(f"Fant {found[0][0]} ({addr})")
            save_address(addr)
        else:
            sys.exit("Fant ikke enheten automatisk. Kjør 'list' for å se parede "
                     "enheter, og bruk --device AA:BB:CC:DD:EE:FF (evt. med --save).")
    if not MAC_RE.match(addr):
        sys.exit(f"Ugyldig MAC-adresse: {addr}")
    return addr


# ---------- Kommunikasjon ----------

def check_bluetooth_support():
    if not (hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")):
        hint = ("Bruk en vanlig python.org-installasjon." if IS_WINDOWS else
                "Installer BlueZ og bruk en Python med Bluetooth-støtte "
                "(f.eks. sudo apt install bluez libbluetooth-dev).")
        sys.exit(f"Denne Python-installasjonen mangler RFCOMM-støtte. {hint}")


def talk(addr, packet, want_reply=False, timeout=5.0):
    check_bluetooth_support()
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(timeout)
    try:
        sock.connect((addr, RFCOMM_CHANNEL))
        sock.sendall(packet)
        print(f"Sendt: {packet.hex(':')}")
        if want_reply:
            return sock.recv(64)
        try:
            reply = sock.recv(64)
            print(f"Svar:  {reply.hex(':')}")
        except socket.timeout:
            pass
    finally:
        sock.close()
    return None


def hexbytes(s):
    return bytes.fromhex(s.replace(":", "").replace(" ", ""))


def crc16(data, crc=0xFFFF):
    """CRC-16/MODBUS (poly 0xA001, init 0xFFFF), lagres little-endian sist i pakken."""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def packet(hexstr):
    """Gjør om en hex-pakke til bytes og regner ut CRC-en på nytt."""
    body = hexbytes(hexstr)[:-2]
    return body + crc16(body).to_bytes(2, "little")


def connection_hint():
    if IS_WINDOWS:
        return ("Tips (Windows): koble til øreproppene i Bluetooth-innstillinger først, "
                "sjekk at adressen stemmer ('list'), og lukk Nothing X-appen hvis den kjører.")
    return ("Tips (Linux): sjekk at øreproppene er paret og tilkoblet "
            "('bluetoothctl connect <adresse>') og at bluetooth-tjenesten kjører.")


# ---------- GUI (Tkinter) ----------

def run_gui():
    import threading
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Nothing Ear")
    root.resizable(False, False)
    pad = {"padx": 10, "pady": 4}

    addr_var = tk.StringVar(value=os.environ.get("NOTHING_EAR_DEVICE") or load_saved_address() or "")
    anc_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Klar")
    lock = threading.Lock()
    buttons = []

    def set_status(text):
        root.after(0, lambda: status_var.set(text))

    def run_bg(work, done=None):
        """Kjør Bluetooth-kall i egen tråd så vinduet ikke fryser."""
        def target():
            with lock:
                try:
                    result = work()
                except (OSError, ValueError, SystemExit) as e:
                    set_status(f"Feil: {e}")
                    return
            if done:
                root.after(0, lambda: done(result))
        threading.Thread(target=target, daemon=True).start()

    def get_addr():
        a = addr_var.get().strip()
        if not MAC_RE.match(a):
            status_var.set("Ugyldig eller manglende adresse (AA:BB:CC:DD:EE:FF)")
            return None
        return a

    def send_cmd(hexstr, label, after=None):
        a = get_addr()
        if not a:
            return
        status_var.set(f"Sender {label}...")

        def work():
            talk(a, packet(hexstr))
            return True

        def done(_):
            status_var.set(f"{label} sendt")
            if load_saved_address() != a:
                save_address(a)
            if after:
                after()
        run_bg(work, done)

    def set_anc():
        mode = anc_var.get()
        send_cmd(PACKETS["anc"][mode], f"ANC: {mode}")

    def read_anc():
        a = get_addr()
        if not a:
            return
        status_var.set("Leser ANC-modus...")

        def work():
            return talk(a, packet(QUERY), want_reply=True)

        def done(resp):
            if resp and len(resp) >= 10:
                name = ANC_BYTE.get(resp[9])
                if name:
                    anc_var.set(name.lower())
                    status_var.set(f"Gjeldende ANC: {name}")
                    return
            status_var.set("Fikk ikke lest ANC-modus")
        run_bg(work, done)

    def search():
        status_var.set("Søker etter enheter...")

        def work():
            return list_devices()

        def done(devs):
            combo["values"] = [f"{mac}  {name}" for name, mac in devs]
            if not devs:
                status_var.set("Ingen parede enheter funnet")
                return
            pick = next((d for d in devs if "nothing" in d[0].lower() or "ear" in d[0].lower()), None)
            if pick:
                addr_var.set(pick[1])
                combo.set(f"{pick[1]}  {pick[0]}")
            status_var.set(f"Fant {len(devs)} enhet(er)")
        run_bg(work, done)

    def on_pick(_event=None):
        addr_var.set(combo.get().split()[0])

    # --- Enhet ---
    f = ttk.LabelFrame(root, text="Enhet")
    f.grid(row=0, column=0, sticky="ew", **pad)
    ttk.Label(f, text="Adresse:").grid(row=0, column=0, **pad)
    ttk.Entry(f, textvariable=addr_var, width=22).grid(row=0, column=1, **pad)
    ttk.Button(f, text="Søk", command=search).grid(row=0, column=2, **pad)
    combo = ttk.Combobox(f, state="readonly", width=40)
    combo.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)
    combo.bind("<<ComboboxSelected>>", on_pick)

    # ANC
    f = ttk.LabelFrame(root, text="Støydemping (ANC)")
    f.grid(row=1, column=0, sticky="ew", **pad)
    for i, mode in enumerate(PACKETS["anc"]):
        tk.Radiobutton(f, text=mode.capitalize(), value=mode, variable=anc_var,
                       indicatoron=False, width=11, pady=4,
                       command=set_anc).grid(row=i // 3, column=i % 3, padx=4, pady=4)
    ttk.Button(f, text="Les gjeldende modus", command=read_anc).grid(
        row=2, column=0, columnspan=3, pady=(2, 6))

    # Andre innstillinger
    f = ttk.LabelFrame(root, text="Innstillinger")
    f.grid(row=2, column=0, sticky="ew", **pad)
    for r, (title, key) in enumerate([("Deteksjon i øret", "in-ear"), ("Lav latency", "latency")]):
        ttk.Label(f, text=title).grid(row=r, column=0, sticky="w", **pad)
        for c, val in enumerate(("on", "off")):
            ttk.Button(f, text="På" if val == "on" else "Av", width=6,
                       command=lambda k=key, v=val, t=title: send_cmd(
                           PACKETS[k][v], f"{t}: {v}")).grid(row=r, column=1 + c, **pad)
    ttk.Button(f, text="Start passformtest for ørepropper",
               command=lambda: send_cmd(FIT_TEST, "Passformtest")).grid(
        row=2, column=0, columnspan=3, pady=(4, 8))

    ttk.Label(root, textvariable=status_var, relief="sunken", anchor="w").grid(
        row=3, column=0, sticky="ew", padx=10, pady=(4, 10))

    if MAC_RE.match(addr_var.get().strip()):
        root.after(300, read_anc)
    root.mainloop()
    return 0


# CLI

def main():
    if len(sys.argv) == 1:
        return run_gui()
    p = argparse.ArgumentParser(description="Styr Nothing Ear (2)")
    p.add_argument("--device", help="Bluetooth-adresse (AA:BB:CC:DD:EE:FF)")
    p.add_argument("--save", action="store_true", help="Lagre adressen til senere")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("gui", help="Åpne grafisk vindu")
    sub.add_parser("list", help="Vis parede Bluetooth-enheter")
    for name in PACKETS:
        sp = sub.add_parser(name)
        sp.add_argument("value", choices=PACKETS[name])
    sub.add_parser("get-anc", help="Les gjeldende ANC-modus")
    sub.add_parser("fit-test", help="Start ear tip fit test")
    raw = sub.add_parser("raw", help="Send egen hex-pakke")
    raw.add_argument("hex")

    args = p.parse_args()

    if args.cmd == "gui":
        return run_gui()

    if args.cmd == "list":
        devices = list_devices()
        if not devices:
            print("Ingen enheter funnet.")
            return 1
        for name, mac in devices:
            print(f"{mac}  {name}")
        return 0

    addr = resolve_address(args.device)
    if args.save:
        save_address(addr)

    try:
        if args.cmd in PACKETS:
            talk(addr, packet(PACKETS[args.cmd][args.value]))
        elif args.cmd == "fit-test":
            talk(addr, packet(FIT_TEST))
        elif args.cmd == "raw":
            talk(addr, hexbytes(args.hex))
        elif args.cmd == "get-anc":
            resp = talk(addr, packet(QUERY), want_reply=True)
            if resp and len(resp) >= 10:
                print(ANC_BYTE.get(resp[9], f"UKJENT ({resp[9]})"))
            else:
                print(f"Uventet svar: {resp.hex(':') if resp else 'ingen'}")
                return 1
    except (OSError, ValueError) as e:
        print(f"Feil: {e}", file=sys.stderr)
        print(connection_hint(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())