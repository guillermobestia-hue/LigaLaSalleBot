# utils.py
import json, os
BASE = os.path.dirname(__file__)
HIST = os.path.join(BASE,"historial.json")

def save_hist(entry):
    if not os.path.exists(HIST):
        with open(HIST,"w",encoding="utf-8") as f:
            json.dump([],f)
    with open(HIST,"r",encoding="utf-8") as f:
        data = json.load(f)
    data.append(entry)
    with open(HIST,"w",encoding="utf-8") as f:
        json.dump(data,f, indent=2, ensure_ascii=False)

def read_hist():
    if not os.path.exists(HIST):
        return []
    with open(HIST,"r",encoding="utf-8") as f:
        return json.load(f)
