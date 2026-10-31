"""Seeded line drift and correlated word lifts; procedural, not learned motion."""
import hashlib
import math
import random

VERSION = 'word-baseline-rhythm-1'


def vertical_advance(base, settings, seed=42, index=0, kind='line'):
    """Bounded extra vertical rhythm above the historical natural setting.

    The old renderer used fixed vertical advances. Values up to the default
    variation retain that behavior; stronger variation adds a little jitter.
    The caller still reserves each line's complete ink bounds.
    """
    key=hashlib.sha256(f'vertical-spacing:{seed}:{index}:{kind}'.encode()).digest()
    noise=random.Random(int.from_bytes(key[:8],'little')).uniform(-1,1)
    extra=max(0,settings['variation']-1)
    return max(1,round(base*settings[kind]*(1+.12*extra*noise)))


def word_offsets(widths, gaps, em, seed=42, line=0, strength=1.):
    """Return bounded raster-pixel lifts; attached punctuation shares its word lift."""
    if not math.isfinite(strength) or not 0 <= strength <= 2:
        raise ValueError('Invalid baseline strength.')
    if not widths:
        return []
    if strength == 0:
        return [0] * len(widths)
    key=hashlib.sha256(f'{VERSION}:{seed}:{line}'.encode()).digest()
    rng=random.Random(int.from_bytes(key[:8],'little'))
    total=max(1,sum(widths)+sum(gaps))
    slope=rng.uniform(-.045,.045)*em
    amplitude=rng.uniform(.012,.032)*em
    phase=rng.uniform(0,math.tau)
    limit=max(1,round(.075*em*strength))
    result=[];x=0;local=0.
    for index,(width,gap) in enumerate(zip(widths,gaps)):
        x+=gap
        if index and not gap:
            result.append(result[-1])
        else:
            local=.5*local+rng.uniform(-.027,.027)*em
            position=(x+width/2)/total
            lift=slope*(position-.5)+amplitude*math.sin(phase+position*math.pi*1.4)+local
            result.append(max(-limit,min(limit,round(lift*strength))))
        x+=width
    return result
