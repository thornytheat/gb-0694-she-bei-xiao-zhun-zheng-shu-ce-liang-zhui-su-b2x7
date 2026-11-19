from datetime import date
from app.numeric import number
from app.errors import DomainError
def day(text):
    try:return date.fromisoformat(text)
    except ValueError:raise DomainError('DATE','日期格式无效')
def volts(value,unit):
    factors={'V':1,'mV':number('0.001')}
    if unit not in factors:raise DomainError('UNIT','电压单位无效')
    return number(value)*factors[unit]
def equivalence(rows):
    parents={}
    def find(x):
        parents.setdefault(x,x)
        if parents[x]!=x:parents[x]=find(parents[x])
        return parents[x]
    for r in rows:
        a,z=find(r['device']),find(r['alias'] or r['device']);parents[max(a,z)]=min(a,z)
    return {x:find(x) for x in list(parents)}
def trace(cert,certs):
    path=[];current=cert;child=None
    while current:
        if current in path:return {'valid':False,'code':'CYCLE','path':path+[current]}
        path.append(current)
        if current not in certs:return {'valid':False,'code':'MISSING_REFERENCE','path':path}
        r=certs[current]
        if r['revoked']=='yes':return {'valid':False,'code':'REVOKED','path':path}
        if child and not day(r['valid_from'])<=day(child['valid_from'])<day(r['valid_to']):return {'valid':False,'code':'REFERENCE_EXPIRED','path':path}
        child=r;current=r['parent']
    return {'valid':True,'code':'TRACEABLE','path':path}
def descendants(start,certs):
    reached={start};todo=[start]
    while todo:
        node=todo.pop()
        for key,value in certs.items():
            if value['parent']==node and key not in reached:reached.add(key);todo.append(key)
    return sorted(reached)

def combine_uncertainty(path,certs):
    """整链标准不确定度合成。

    溯源路径上同一份证书（同一上级标准器，可能在多级证书中重复出现）只计一次，
    避免按每份证书独立累加导致的过度保守（合格件大范围退回）；
    共享上级作为共同系统分量保留在合成结果中，而不是当作互不相关的随机量跨测量平均抵消。
    去重后的独立标准不确定度按RSS（方和根）合成 u_c = sqrt(sum(u_i^2))。
    返回 (u_c, 来源列表, 缺失证书列表, 线性累加基线u_linear)。
    """
    sources=[];seen=set();missing=[];linear=number('0')
    for node in path:
        if node in seen:continue
        seen.add(node)
        record=certs.get(node) or {}
        if record.get('unc_missing',True) or record.get('unc_v') is None:
            missing.append(node);continue
        u=number(record['unc_v'])
        sources.append({'证书':node,'标准不确定度_V':str(u),'覆盖因子':record.get('coverage_k') or '2'})
        linear+=u
    if missing:return None,sources,missing,None
    squared=sum((number(s['标准不确定度_V'])**2 for s in sources),number('0'))
    uc=squared.sqrt()
    return uc,sources,missing,linear

def guard_band_verdict(value, spec_lo, spec_hi, expanded):
    """护基判定（ISO 14253-1思路）：以扩展不确定度U构造验收区间。

    完整区间[value-U, value+U]落在允许偏差内才判符合；整体落在偏差外判不符合；
    跨在边界上（区间与规格限相交）判无法判定。边界相切按符合处理（不拒绝原假设）。
    """
    low=value-expanded;high=value+expanded
    if low>=spec_lo and high<=spec_hi:return '符合'
    if high<spec_lo or low>spec_hi:return '不符合'
    return '无法判定'
