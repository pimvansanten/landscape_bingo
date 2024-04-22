import random
from pandas import DataFrame, concat
kleuren = [
    "Aqua",
    "Muisgrijs",
    "Roze",
    "Turquoise",
    "Blauw",
    "Paars",
    "Groen"]
out = [DataFrame({"kleur": kleuren, "reeks": [0]*7})]
for i in range(1, 30):
    lijstje = random.sample(kleuren, k=7)
    while lijstje[0] == out[-1].loc[6, "kleur"]:
        lijstje = random.sample(kleuren, k=7)        
    out.append(DataFrame({"kleur": lijstje, "reeks": [i]*7}))

df = concat(out)
print(df.to_string(index=False))

