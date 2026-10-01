# nothing-ear-py

Unofficial Python controller for **Nothing Ear (2)** and **Nothing Ear (2024)** earbuds. Works on **Windows and Linux**, with both a command-line interface and a small graphical window. Uses only the Python standard library.

> Not affiliated with or endorsed by Nothing Technology Limited. Use at your own risk.

## Features

- Switch noise cancellation: Transparency, Off, High, Mid, Low, Adaptive
- Read the current ANC mode
- Turn in-ear detection on/off
- Turn low-latency mode on/off
- Start the ear tip fit test
- List paired Bluetooth devices and auto-detect your earbuds
- Send raw packets for experimenting
- Simple Tkinter GUI

## Compatibility

| Device | Status |
| --- | --- |
| Nothing Ear (2024) | Tested on Windows (command line) |
| Nothing Ear (2) | Protocol was reverse-engineered for this model, but not tested with this script |
| Other Nothing / CMF earbuds | Untested; they may share the protocol but could use different packets |

Not every command is guaranteed to work on every model.

## Requirements

- Python 3.8 or newer, with Bluetooth socket support (the standard python.org installer on Windows has it)
- Earbuds **paired and connected** in your operating system's Bluetooth settings
- **Linux:** BlueZ (`bluetoothctl`). For the GUI you may need Tkinter: `sudo apt install python3-tk`
- **Windows:** nothing extra. Close the Nothing X app if it is running

## Usage

Find your earbuds' Bluetooth address:

```
python ear2.py list
```

Send a first command and save the address for later:

```
python ear2.py --device AA:BB:CC:DD:EE:FF --save anc transparency
```

After that the address is remembered:

```
python ear2.py anc high          # high, mid, low, adaptive, off, transparency
python ear2.py get-anc           # print the current ANC mode
python ear2.py in-ear on         # or off
python ear2.py latency on        # or off
python ear2.py fit-test
python ear2.py raw 55:60:01:...  # send your own packet, sent as-is
```

On Linux, use `python3` instead of `python`.

### GUI

Run the script with no arguments (or `python ear2.py gui`) to open the window:

```
python ear2.py
```

Use **Søk** to find paired devices, pick your earbuds, and click an ANC mode. The GUI shows the current mode on startup if an address is saved.

### Configuration

The device address is looked up in this order:

1. `--device` argument
2. `NOTHING_EAR_DEVICE` environment variable
3. Saved config at `~/.nothing-ear/config.json`
4. Automatic detection of a paired device with "Nothing" or "Ear" in its name

## How it works

The earbuds speak a simple binary protocol over Bluetooth Classic **RFCOMM, channel 15**. Each packet starts with `55 60 01`, followed by a command, length, sequence byte, payload, and a 16-bit checksum (CRC-16/MODBUS, stored little-endian) at the end. The script recalculates the checksum before sending every predefined command.

Example, ANC transparency mode:

```
55:60:01:0f:f0:03:00:cb:01:07:00:c5:af
```

## Troubleshooting

- **Connection error:** make sure the earbuds are connected (not just paired) in your system's Bluetooth settings, and that the address is correct (`python ear2.py list`).
- **"Missing RFCOMM support" error:** your Python build lacks Bluetooth sockets. On Windows use the python.org installer; on Linux install BlueZ and its development headers.
- **Linux permission errors:** you may need to be in the `bluetooth` group: `sudo usermod -aG bluetooth $USER`, then log out and back in.
- **Command sent but nothing happens:** your model may use a different packet for that function. Use `raw` to experiment, and open an issue if you find one that works.

## Credits

The protocol was reverse-engineered by **Bharadwaj Raju**: [Creating a Linux controller for the Nothing Ear (2)](https://bharadwajraju.com/posts/nothing-ear-2-on-linux/). Many thanks.

## License

MIT. Add a `LICENSE` file to the repository.
