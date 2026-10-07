"""Small runnable adaptation of literal_integrity's span/placeholder checks.

The caller supplies reviewed spans. Production formula classification and image
region policies are intentionally outside this excerpt. No Unicode compatibility
normalization is applied to the stored literals.
"""
from dataclasses import dataclass
from hashlib import sha256
import re

TOKEN=re.compile(r'__LITERAL_\d+_[0-9A-F]{12}__')
@dataclass(frozen=True)
class Plan:
    source: str
    request: str
    raw: tuple[str,...]
    tokens: tuple[str,...]

def protect(source: str, spans: list[tuple[int,int]]) -> Plan:
    cursor=0; parts=[]; raw=[]; tokens=[]
    for index,(start,end) in enumerate(sorted(spans)):
        if not cursor<=start<end<=len(source): raise ValueError('overlapping or invalid span')
        value=source[start:end]
        token=f'__LITERAL_{index}_{sha256(value.encode()).hexdigest()[:12].upper()}__'
        if TOKEN.search(source): raise ValueError('source collides with placeholder namespace')
        parts.extend((source[cursor:start],token)); raw.append(value); tokens.append(token); cursor=end
    parts.append(source[cursor:])
    return Plan(source,''.join(parts),tuple(raw),tuple(tokens))

def restore(plan: Plan, candidate: str, *, allow_reordering=False) -> tuple[str,bool]:
    actual=TOKEN.findall(candidate)
    expected=list(plan.tokens)
    if (sorted(actual) if allow_reordering else actual)!=(sorted(expected) if allow_reordering else expected):
        return plan.source,False
    for token,raw in zip(plan.tokens,plan.raw):
        digest=sha256(raw.encode()).hexdigest()[:12].upper()
        if candidate.count(token)!=1 or digest not in token: return plan.source,False
        candidate=candidate.replace(token,raw)
    return candidate,True

if __name__=='__main__':
    source='孔径 Ø 12 ± 0.10 mm'; start=source.index('Ø')
    plan=protect(source,[(start,len(source))])
    print(restore(plan,plan.request.replace('孔径','Bore')))
