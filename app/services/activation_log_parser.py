import re
from pathlib import Path

def extract_twitch_activation(log_path: Path, lines: int = 10):
    """
    Extrahiere Twitch-Activation-Link und Code aus den letzten Zeilen der Logdatei.
    Gibt ein Dict mit 'activation_url' und 'activation_code' zurück, falls gefunden.
    """
    result = {"activation_url": None, "activation_code": None}
    if not log_path.exists():
        return result
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        log_lines = f.readlines()[-lines:]
    found_url = False
    found_code = None

    for line in log_lines:
        if re.search(r"https://www\.twitch\.tv/activate", line):
            found_url = True

        code_match = re.search(r"enter this code: ([A-Z0-9]{6,})", line)
        if code_match:
            found_code = code_match.group(1)

    # Nur wenn ein Code vorhanden ist, sollen Activation-Daten geliefert werden.
    if found_code:
        result["activation_code"] = found_code
        result["activation_url"] = "https://www.twitch.tv/activate" if found_url else None

    return result
