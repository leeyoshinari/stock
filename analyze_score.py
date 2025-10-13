import re
import json

file_path = '/Users/ljc/Downloads/aaa.txt'
res_path = '/Users/ljc/Downloads/bbb.txt'
score = []
pattern = re.compile(
    r"signals=\s*(\d+)\s*\|\s*hit=([\d\.]+)%\s*\|\s*avg=([\-\d\.]+)%\s*\|\s*max_drawDown=([\-\d\.]+)%"
)

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for line in lines:
        res = {}
        split_line = line.split('-')
        p = split_line[-1]

        results = pattern.findall(line)

        signals, hit, avg, max_drawdown = results[0]
        res = {
            "signals": int(signals),
            "hit": float(hit),
            "avg": float(avg),
            "max_drawDown": float(max_drawdown)
        }
        res.update({"param": json.loads(p)})
        score.append(res)

score.sort(key=lambda x: (-x['hit'], -x['avg']))

with open(res_path, 'w', encoding='utf-8') as f:
    for s in score:
        f.write(json.dumps(s) + '\n')
