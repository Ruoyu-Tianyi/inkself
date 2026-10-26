"""Seeded line drift and correlated word lifts; procedural, not learned motion."""
import hashlib
import math
import random

VERSION = 'word-baseline-rhythm-1'


def word_offsets(widths, gaps, em, seed=42, line=0):
    """Return bounded raster-pixel lifts; attached punctuation shares its word lift."""
    if not widths:
        return []
    key=hashlib.sha256(f'{VERSION}:{seed}:{line}'.encode()).digest()
    rng=random.Random(int.from_bytes(key[:8],'little'))
    total=max(1,sum(widths)+sum(gaps))
    slope=rng.uniform(-.045,.045)*em
    amplitude=rng.uniform(.012,.032)*em
    phase=rng.uniform(0,math.tau)
    limit=max(1,round(.075*em))
    result=[];x=0;local=0.
    for index,(width,gap) in enumerate(zip(widths,gaps)):
        x+=gap
        if index and not gap:
            result.append(result[-1])
        else:
            local=.5*local+rng.uniform(-.027,.027)*em
            position=(x+width/2)/total
            lift=slope*(position-.5)+amplitude*math.sin(phase+position*math.pi*1.4)+local
            result.append(max(-limit,min(limit,round(lift))))
        x+=width
    return result
