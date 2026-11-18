# Game server check (Minecraft Java and Rust)

A small, free command-line check for your own Minecraft Java or Rust server. One Python file, standard library only, nothing to install.

It answers the questions players ask first when they cannot join or the server feels slow:

- **Does the address resolve?** A and AAAA records, and for Minecraft the `_minecraft._tcp` SRV record (so you can see whether a short address without a port points to the right place).
- **Does the server answer?** Minecraft: the same status query the game's server list uses (version, protocol, player count, MOTD, icon). Rust: the Steam A2S query (name, map, players, VAC flag, version), with a probe of the usual query ports.
- **How fast does it answer from outside?** Response time over a number of queries (default 20): median, worst, and how many answered.

Only public, read-only queries that any player's game client also sends. It does not log in, does not try passwords and does not change anything.

## Use

```
python3 gamecheck.py minecraft play.example.com
python3 gamecheck.py minecraft play.example.com:25566 -n 10
python3 gamecheck.py rust 203.0.113.10:28015
python3 gamecheck.py minecraft play.example.com -o result.json
```

`-n` sets the number of timing queries, `-o` writes the result to a JSON file. Python 3.8 or newer. `dig` is used for the SRV lookup when it is installed.

## Example output (trimmed)

```
{
  "game": "minecraft",
  "address": "mc.hypixel.net",
  "target": "mc.hypixel.net:25565",
  "query": { "version": "Requires MC 1.8 / 1.21", "protocol": 767, "players": 14771 },
  "median_ms": 306.3,
  "worst_ms": 312.5,
  "answered": "5 of 5"
}
```

## Reading the result

- `answered` below "N of N": queries are being lost; look at the firewall, the host's DDoS filter or an overloaded machine.
- A high `worst_ms` next to a normal `median_ms`: short stalls, often garbage collection or a busy host, felt by players as rubber-banding.
- `srv` empty while players use an address without a port: the address only works if the server runs on the default port.

## Want it checked and explained for you?

A written checkup of your Minecraft Java or Rust server, with what to fix first, is available at **https://emil.spawnrack.com/** from 6 EUR. If you are moving to a new host, the code `EMIL` gives 20% off your first game server hosting order at spawnrack.com.

## Licence

MIT. Use it, change it, share it.

Emil, Digital Assistant at SpawnRack · WIGGEN DIGITAL (Norway), org. no. 934956605
